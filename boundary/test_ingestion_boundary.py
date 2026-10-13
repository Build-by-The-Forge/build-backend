"""Ingestion across the real boundary: dispatch, the AI worker, signed
callbacks to the backend, reconciliation.

C3/C7/C9/C10/C12 at the backend callback, C16, C19-C23.

Phase 1 has no real ingestion pipeline (plan §13). The shipped worker
therefore fails every task with INGESTION_PIPELINE_UNAVAILABLE. C22 is
verified as re-scoped in M3-08: the full signed path runs end to end, the
job ends `failed` with that error, and nothing makes it `ready` without
stage evidence.
"""

import uuid

import pytest

from boundary.conftest import (
    A2B,
    AI_ID,
    B2A,
    CALLBACK_PATH,
    create_job,
    get_job,
    jbytes,
    sign,
    system_context,
    to_ai,
    to_backend,
    wait_for_status,
)

TERMINAL = {"failed", "ready"}


@pytest.fixture(scope="module")
def dispatched(backend, tenant_a):
    """A tenant-A job dispatched through the backend to the real AI-service and
    processed by the real worker, whose signed callback reached the backend."""
    job = create_job(backend, tenant_a)
    response = backend.post(f"/content/jobs/{job['id']}/dispatch", headers=tenant_a.h("lecturer"))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "processing"
    return wait_for_status(backend, tenant_a, job["id"], TERMINAL)


def event(job: dict, **overrides) -> dict:
    body = {
        "job_id": job["id"],
        "event_id": str(uuid.uuid4()),
        "event_type": "stage_progress",
        "stage": "extracted",
        "external_task_id": job["external_task_id"],
        "run_number": job["run_number"],
        "attempt_count": job["attempt_count"],
        "metrics": {"characters": 900, "pages": 3, "method": "native_text"},
    }
    body.update(overrides)
    return body


def post_callback(backend, body: dict, tenant_id: str, **kw):
    raw = jbytes(body)
    return backend.post(CALLBACK_PATH, content=raw, headers=to_backend(CALLBACK_PATH, raw, system_context(tenant_id), **kw))


def processing_job(backend, tenant):
    """A job in `processing` with an external task id, without the worker
    racing the test: dispatched for real, then reconciled state is ignored."""
    job = create_job(backend, tenant)
    dispatched = backend.post(f"/content/jobs/{job['id']}/dispatch", headers=tenant.h("lecturer"))
    assert dispatched.status_code == 200, dispatched.text
    return dispatched.json()["data"]


# --- C22 (re-scoped) and C18: the full signed path ------------------------------------------


def test_c22_dispatch_worker_and_signed_callback_reach_the_backend(dispatched):
    # The worker reported through BACKEND_CALLBACK_URL (C18: the only
    # destination), signed; the backend applied it to the tenant's job.
    assert dispatched["status"] == "failed", dispatched
    assert dispatched["error_code"] == "INGESTION_PIPELINE_UNAVAILABLE"
    assert dispatched["external_task_id"].startswith("task_")


def test_c22_the_job_never_becomes_ready_without_stage_evidence(backend, tenant_a, dispatched):
    completed = event(dispatched, event_type="job_completed", stage=None, metrics={})
    response = post_callback(backend, completed, tenant_a.tenant_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSITION_NOT_ALLOWED"
    assert get_job(backend, tenant_a, dispatched["id"])["status"] == "failed"


# --- C23: reconciliation ------------------------------------------------------------------


def test_c23_reconcile_reflects_ai_service_task_state(backend, tenant_a):
    job = processing_job(backend, tenant_a)
    # Whether or not the worker's callback already landed, reconcile brings
    # the job to AI-service's recorded outcome, or refuses because it is
    # already terminal.
    response = backend.post(f"/content/jobs/{job['id']}/reconcile", headers=tenant_a.h("lecturer"))
    assert response.status_code in (200, 409), response.text
    final = wait_for_status(backend, tenant_a, job["id"], TERMINAL)
    assert (final["status"], final["error_code"]) == ("failed", "INGESTION_PIPELINE_UNAVAILABLE")


def test_c23_ai_service_task_status_is_tenant_scoped(ai, backend, tenant_a, tenant_b, dispatched):
    path = f"/v1/ingest/tasks/{dispatched['external_task_id']}"
    own = ai.get(path, headers=to_ai("GET", path, b"", system_context(tenant_a.tenant_id)))
    other = ai.get(path, headers=to_ai("GET", path, b"", system_context(tenant_b.tenant_id)))
    assert own.status_code == 200, own.text
    assert own.json()["job_id"] == dispatched["id"]
    assert other.status_code == 404


# --- C16: tenant A cannot operate tenant B's job ---------------------------------------


@pytest.mark.parametrize(
    "method,suffix",
    [("GET", ""), ("POST", "/dispatch"), ("POST", "/retry"), ("POST", "/reconcile")],
)
def test_c16_another_tenants_job_is_404(backend, tenant_a, tenant_b, dispatched, method, suffix):
    response = backend.request(
        method, f"/content/jobs/{dispatched['id']}{suffix}", headers=tenant_b.h("lecturer"), json={} if method == "POST" else None
    )
    assert response.status_code == 404
    assert get_job(backend, tenant_a, dispatched["id"])["status"] == "failed"


def test_c16_another_tenants_asset_cannot_be_reprocessed(backend, tenant_a, tenant_b, dispatched):
    response = backend.post(f"/content/assets/{dispatched['asset_id']}/reprocess", json={}, headers=tenant_b.h("lecturer"))
    assert response.status_code == 404


# --- C19-C21: callbacks cannot cross tenants, create state, regress or duplicate -------


def test_c19_a_callback_naming_another_tenant_is_404_and_changes_nothing(backend, tenant_a, tenant_b):
    job = processing_job(backend, tenant_a)
    response = post_callback(backend, event(job), tenant_b.tenant_id)
    assert response.status_code == 404


def test_c20_a_callback_for_an_unknown_job_is_404(backend, tenant_a):
    job = {"id": str(uuid.uuid4()), "external_task_id": "task_unknown", "run_number": 1, "attempt_count": 1}
    assert post_callback(backend, event(job), tenant_a.tenant_id).status_code == 404


def worker_events(ai, tenant, job) -> list[dict]:
    path = f"/v1/ingest/tasks/{job['external_task_id']}"
    response = ai.get(path, headers=to_ai("GET", path, b"", system_context(tenant.tenant_id)))
    assert response.status_code == 200, response.text
    return response.json()["events"]


def test_c21_the_workers_own_callback_replayed_is_a_duplicate(ai, backend, tenant_a, dispatched):
    [*_, failed] = worker_events(ai, tenant_a, dispatched)
    assert failed["event_type"] == "job_failed"

    response = post_callback(backend, failed, tenant_a.tenant_id)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["outcome"] == "duplicate"


def test_c21_the_same_event_id_with_other_content_is_409(ai, backend, tenant_a, dispatched):
    [*_, failed] = worker_events(ai, tenant_a, dispatched)
    response = post_callback(backend, {**failed, "error_message": "rewritten"}, tenant_a.tenant_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_CONFLICT"


@pytest.mark.parametrize(
    "change",
    [{"attempt_count": 2}, {"run_number": 2}, {"external_task_id": "task_other"}],
    ids=["other-attempt", "other-run", "other-task"],
)
def test_c21_events_for_another_attempt_are_stale(backend, tenant_a, dispatched, change):
    response = post_callback(backend, event(dispatched, **change), tenant_a.tenant_id)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["outcome"] == "stale"


@pytest.mark.parametrize(
    "body",
    [
        {"event_type": "stage_progress", "stage": "extracted"},
        {"event_type": "job_completed", "stage": None, "metrics": {}},
    ],
    ids=["failed-to-extracted", "failed-to-ready"],
)
def test_c21_a_failed_job_cannot_move_again(backend, tenant_a, dispatched, body):
    response = post_callback(backend, event(dispatched, **body), tenant_a.tenant_id)
    assert response.status_code == 409
    job = get_job(backend, tenant_a, dispatched["id"])
    assert (job["status"], job["error_code"]) == ("failed", "INGESTION_PIPELINE_UNAVAILABLE")


# --- Protocol at the backend callback (C3, C7, C9, C10, C12) ---------------------------------


def unknown_job_callback(tenant_id: str):
    job = {"id": str(uuid.uuid4()), "external_task_id": "task_x", "run_number": 1, "attempt_count": 1}
    raw = jbytes(event(job))
    return raw, to_backend(CALLBACK_PATH, raw, system_context(tenant_id))


def test_c3_a_callback_body_changed_after_signing_is_401(backend, tenant_a):
    raw, headers = unknown_job_callback(tenant_a.tenant_id)
    assert (
        backend.post(CALLBACK_PATH, content=raw.replace(b"stage_progress", b"job_completed"), headers=headers).status_code == 401
    )


def test_c7_a_callback_signed_with_the_backend_to_ai_secret_is_401(backend, tenant_a):
    raw = jbytes(event({"id": "j", "external_task_id": "t", "run_number": 1, "attempt_count": 1}))
    headers = sign(
        sender=AI_ID, secret=B2A, method="POST", target=CALLBACK_PATH, body=raw, context=system_context(tenant_a.tenant_id)
    )
    assert backend.post(CALLBACK_PATH, content=raw, headers=headers).status_code == 401


def test_c9_a_replayed_callback_is_401(backend, tenant_a):
    raw, headers = unknown_job_callback(tenant_a.tenant_id)
    assert backend.post(CALLBACK_PATH, content=raw, headers=headers).status_code == 404
    assert backend.post(CALLBACK_PATH, content=raw, headers=headers).status_code == 401


def test_c10_a_callback_missing_its_signature_is_401(backend, tenant_a):
    raw, headers = unknown_job_callback(tenant_a.tenant_id)
    del headers["X-BUILD-Signature"]
    assert backend.post(CALLBACK_PATH, content=raw, headers=headers).status_code == 401


@pytest.mark.parametrize("secret", [A2B, B2A, "build-ai-dev-webhook-secret"])
def test_c12_bearer_on_the_callback_is_401(backend, tenant_a, secret):
    raw, _ = unknown_job_callback(tenant_a.tenant_id)
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    assert backend.post(CALLBACK_PATH, content=raw, headers=headers).status_code == 401


def test_c17_users_cannot_drive_job_state(backend, tenant_a, dispatched):
    for suffix in ("/start", "/progress", "/complete", "/fail"):
        response = backend.post(f"/content/jobs/{dispatched['id']}{suffix}", json={}, headers=tenant_a.h("owner"))
        assert response.status_code in (404, 405)
