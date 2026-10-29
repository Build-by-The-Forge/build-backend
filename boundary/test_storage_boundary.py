"""Uploaded documents across the backend and AI-service boundary (P3-1
PR 6), against the m3 topology's real SeaweedFS.

C22 here proves the verified fetch: the ready job's evidence (see
conftest.pipeline_outcome) records the fetched document's SHA-256, size
and type.

The storage_down cases run only while object storage is stopped
(scripts/m3_boundary_gate.sh stops it, as it does Redis for C11).
"""

import hashlib
import os
import time
import uuid

import pytest

from boundary.conftest import (
    create_asset,
    create_job_for,
    create_source,
    jbytes,
    object_key,
    object_store,
    pdf_document,
    pipeline_outcome,
    system_context,
    to_ai,
    upload,
    user_context,
    wait_for_status,
)

DISPATCH = "/v1/ingest/dispatch"
BUCKET = "build-documents"
BACKEND_APP_DSN = os.environ.get("BOUNDARY_BACKEND_APP_DSN", "")
TERMINAL_STATES = {"failed", "ready"}
# A fetch-and-verify task normally finishes in about a second; the worker is
# shared with every other test, so allow for a queue.
FETCH_TIMEOUT = 180


def dispatch(backend, tenant, job_id):
    return backend.post(f"/content/jobs/{job_id}/dispatch", headers=tenant.h("lecturer"))


# --- the happy path: a verified fetch, whatever the pipeline then does ----------------------


def test_c22_the_ai_fetches_and_verifies_the_uploaded_document(backend, tenant_a):
    document = pdf_document()
    asset = create_asset(backend, tenant_a, document)
    job = create_job_for(backend, tenant_a, asset)

    final = wait_for_status(backend, tenant_a, job["id"], TERMINAL_STATES, timeout=FETCH_TIMEOUT)

    fetch = pipeline_outcome(final)
    assert fetch["verified"] is True
    assert (fetch["sha256"], fetch["size_bytes"]) == (hashlib.sha256(document).hexdigest(), len(document))
    assert fetch["mime_type"] == "application/pdf"


# --- integrity: caught by whichever side can see it -------------------------------------------


def test_a_tampered_object_is_refused_by_the_ai_service(backend, tenant_a):
    """Same size, other bytes, written without the backend's SHA-256
    metadata: the backend's head check cannot tell, the AI's hash does."""
    document = pdf_document()
    asset = create_asset(backend, tenant_a, document)
    object_store().put_object(Bucket=BUCKET, Key=object_key(asset), Body=document[:-1] + b"X")
    job = create_job_for(backend, tenant_a, asset)

    final = wait_for_status(backend, tenant_a, job["id"], TERMINAL_STATES, timeout=FETCH_TIMEOUT)

    assert (final["status"], final["error_code"], final["is_retryable"]) == (
        "failed",
        "ASSET_INTEGRITY_MISMATCH",
        False,
    )


def test_a_missing_object_is_refused_before_the_ai_service(backend, tenant_a):
    asset = create_asset(backend, tenant_a)
    object_store().delete_object(Bucket=BUCKET, Key=object_key(asset))
    job = create_job_for(backend, tenant_a, asset)
    final = wait_for_status(backend, tenant_a, job["id"], TERMINAL_STATES, timeout=FETCH_TIMEOUT)

    assert (final["status"], final["error_code"], final["external_task_id"]) == (
        "failed",
        "ASSET_OBJECT_MISSING",
        None,
    )


def test_an_object_resized_in_storage_is_refused_before_the_ai_service(backend, tenant_a):
    asset = create_asset(backend, tenant_a)
    object_store().put_object(Bucket=BUCKET, Key=object_key(asset), Body=b"%PDF-1.7 short")
    job = create_job_for(backend, tenant_a, asset)
    final = wait_for_status(backend, tenant_a, job["id"], TERMINAL_STATES, timeout=FETCH_TIMEOUT)

    assert (final["status"], final["error_code"], final["external_task_id"]) == (
        "failed",
        "ASSET_OBJECT_MISMATCH",
        None,
    )


# --- authorization: the AI never fetches another tenant's object -----------------------------


def test_another_tenants_storage_reference_is_rejected_by_the_ai_service(ai, backend, tenant_a, tenant_b):
    """A signed dispatch for tenant B naming tenant A's object (as a
    compromised or buggy caller might): the AI resolves references only
    within the verified tenant's prefix."""
    asset = create_asset(backend, tenant_a)
    body = {
        "job_id": f"bnd-job-{uuid.uuid4().hex[:12]}",
        "asset_id": asset["id"],
        "source_id": asset["source_id"],
        "run_number": 1,
        "attempt_count": 1,
        "idempotency_key": f"bnd-{uuid.uuid4().hex}",
        "mime_type": "application/pdf",
        "content_sha256": asset["content_sha256"],
        "file_size_bytes": asset["file_size_bytes"],
        "storage_uri": asset["storage_uri"],
        "correlation_id": "boundary",
    }
    raw = jbytes(body)
    context = user_context(tenant_b.tenant_id, str(uuid.uuid4()), ["content.job.manage"])
    accepted = ai.post(DISPATCH, content=raw, headers=to_ai("POST", DISPATCH, raw, context))
    assert accepted.status_code == 202, accepted.text
    task_id = accepted.json()["external_task_id"]

    path = f"/v1/ingest/tasks/{task_id}"
    deadline = time.time() + 60
    while True:
        status = ai.get(path, headers=to_ai("GET", path, b"", system_context(tenant_b.tenant_id))).json()
        if status["state"] in ("failed", "succeeded") or time.time() > deadline:
            break
        time.sleep(0.5)

    assert status["state"] == "failed", status
    assert status["events"][-1]["error_code"] == "ASSET_REFERENCE_REJECTED"


# --- limits ------------------------------------------------------------------------------------


def test_an_upload_over_the_limit_is_refused(backend, tenant_a):
    source_id = create_source(backend, tenant_a)
    too_large = b"%PDF-1.7\n" + b"x" * (25 * 1024 * 1024)  # over the 25 MiB default

    response = upload(backend, tenant_a, source_id, too_large)

    assert response.status_code == 413, response.text[:200]


# --- object storage stopped ----------------------------------------------------------------


async def _seed_managed_asset(tenant_id: str, source_id: str) -> str:
    """An asset row exactly as an upload writes it, inserted directly:
    nothing can be uploaded while storage is down."""
    import json
    from datetime import datetime, timezone

    import asyncpg

    asset_id = str(uuid.uuid4())
    sha = hashlib.sha256(pdf_document()).hexdigest()
    now = datetime.now(timezone.utc)
    conn = await asyncpg.connect(BACKEND_APP_DSN)
    try:
        await conn.execute(
            """INSERT INTO content_assets (id, source_id, tenant_id, file_name, mime_type, file_size_bytes,
                   content_sha256, storage_uri, asset_version, parent_asset_id, status, ingestion_status,
                   metadata, created_by, created_by_email, created_at, updated_at)
               VALUES ($1, $2, $3, 'outage.pdf', 'application/pdf', 100, $4, $5, 1, NULL, 'active',
                   'uploaded', $6, 'boundary', 'boundary@build.internal', $7, $7)""",
            asset_id,
            source_id,
            tenant_id,
            sha,
            f"s3://{BUCKET}/tenants/{tenant_id}/assets/{asset_id}/{sha}",
            json.dumps({}),
            now,
        )
    finally:
        await conn.close()
    return asset_id


@pytest.mark.storage_down
def test_an_upload_while_storage_is_down_is_a_retryable_503(backend, tenant_a):
    response = upload(backend, tenant_a, create_source(backend, tenant_a), pdf_document())

    assert response.status_code == 503, response.text
    assert response.headers["Retry-After"] == "5"
    assert response.json()["error"]["code"] == "OBJECT_STORAGE_UNAVAILABLE"


@pytest.mark.storage_down
def test_a_dispatch_while_storage_is_down_is_retryable_and_never_reaches_the_ai(backend, tenant_a):
    import asyncio

    asset_id = asyncio.run(_seed_managed_asset(tenant_a.tenant_id, create_source(backend, tenant_a)))
    job = create_job_for(backend, tenant_a, {"id": asset_id})

    response = dispatch(backend, tenant_a, job["id"])

    assert response.status_code == 503, response.text
    assert response.headers["Retry-After"] == "5"
    assert response.json()["error"]["code"] == "OBJECT_STORAGE_UNAVAILABLE"
    assert response.json()["data"]["is_retryable"] is True
    assert response.json()["data"]["external_task_id"] is None
