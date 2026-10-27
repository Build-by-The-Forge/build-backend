"""Real two-service boundary suite (M3 design Part C).

Runs inside the combined topology (deploy/compose.m3.yml, service
``boundary-tests``) against the real backend, the real AI-service, its
worker, PostgreSQL 17 with the least-privilege roles and Redis 8. Nothing is
mocked. Run it with scripts/m3_boundary_gate.sh.

Setup goes through the product's own paths: tenants and owners come from
scripts/provision_tenant.py; other members are invited, register, verify their
email and accept, with one-time codes read from the development email outbox
the backend writes to a shared volume.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

BACKEND_URL = os.environ.get("BOUNDARY_BACKEND_URL", "")
AI_URL = os.environ.get("BOUNDARY_AI_URL", "")
B2A = os.environ.get("BACKEND_TO_AI_SECRET", "")
A2B = os.environ.get("AI_TO_BACKEND_SECRET", "")
OUTBOX = Path(os.environ.get("EMAIL_OUTBOX_PATH", "/outbox/emails.jsonl"))
AI_APP_DSN = os.environ.get("BOUNDARY_AI_APP_DSN", "")

if not (BACKEND_URL and AI_URL and B2A and A2B):
    pytest.skip("boundary suite runs only inside the M3 topology", allow_module_level=True)


def pytest_configure(config):
    config.addinivalue_line("markers", "redis_down: C11, run only while Redis is stopped")
    config.addinivalue_line("markers", "storage_down: P3-1, run only while object storage is stopped")


BACKEND_ID = "build-backend"
AI_ID = "ai-service"
CALLBACK_PATH = "/content/ingestion/callbacks"
PASSWORD = "Boundary-Pass-2026!"


# --- BUILD Service Signature v1, written out in full ---------------------------------
#
# The suite signs with its own small implementation (not either service's
# module) so that a forged request differs from a valid one only where a test
# says so.


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def user_context(
    tenant_id: str,
    user_id: str,
    permissions: list[str],
    *,
    membership_id: str | None = None,
    role: str = "lecturer",
) -> dict[str, Any]:
    return {
        "v": 1,
        "actor": "user",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "membership_id": membership_id or str(uuid.uuid4()),
        "role": role,
        "permissions": sorted(permissions),
        "correlation_id": "boundary",
    }


def system_context(tenant_id: str) -> dict[str, Any]:
    return {
        "v": 1,
        "actor": "system",
        "tenant_id": tenant_id,
        "user_id": None,
        "membership_id": None,
        "role": None,
        "permissions": [],
        "correlation_id": "boundary",
    }


def sign(
    *,
    sender: str,
    secret: str,
    method: str,
    target: str,
    body: bytes,
    context: dict[str, Any] | None = None,
    context_raw: bytes | None = None,
    timestamp: int | None = None,
    request_id: str | None = None,
) -> dict[str, str]:
    raw = context_raw if context_raw is not None else canonical_json(context or {})
    ts = str(int(time.time()) if timestamp is None else timestamp)
    rid = request_id or str(uuid.uuid4())
    canonical = "\n".join(
        (
            "v1",
            sender,
            method.upper(),
            target,
            ts,
            rid,
            hashlib.sha256(body).hexdigest(),
            hashlib.sha256(raw).hexdigest(),
        )
    ).encode()
    signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return {
        "X-BUILD-Service": sender,
        "X-BUILD-Timestamp": ts,
        "X-BUILD-Request-ID": rid,
        "X-BUILD-Context": b64url(raw),
        "X-BUILD-Signature": f"v1={signature}",
        "Content-Type": "application/json",
    }


def to_ai(method: str, target: str, body: bytes, context: dict[str, Any], **kw: Any) -> dict[str, str]:
    return sign(sender=BACKEND_ID, secret=B2A, method=method, target=target, body=body, context=context, **kw)


def to_backend(target: str, body: bytes, context: dict[str, Any], **kw: Any) -> dict[str, str]:
    return sign(sender=AI_ID, secret=A2B, method="POST", target=target, body=body, context=context, **kw)


def jbytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value).encode()


# --- HTTP ------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def backend() -> httpx.Client:
    with httpx.Client(base_url=BACKEND_URL, timeout=30, follow_redirects=False) as client:
        yield client


@pytest.fixture(scope="session")
def ai() -> httpx.Client:
    with httpx.Client(base_url=AI_URL, timeout=30, follow_redirects=False) as client:
        yield client


# --- Tenants and members through the product's own paths ------------------------------


def outbox_code(to: str, subject_prefix: str, after: int = 0) -> str:
    deadline = time.time() + 10
    while time.time() < deadline:
        if OUTBOX.exists():
            lines = OUTBOX.read_text(encoding="utf-8").splitlines()[after:]
            for line in reversed(lines):
                message = json.loads(line)
                if message["to"] == to and message["subject"].startswith(subject_prefix):
                    return message["body"].split("\n\n")[1].strip()
        time.sleep(0.2)
    raise AssertionError(f"no {subject_prefix!r} email for {to} in {OUTBOX}")


@dataclass
class Member:
    email: str
    user_id: str
    token: str
    role: str
    membership_id: str = ""

    def headers(self, slug: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Tenant-Slug": slug}


@dataclass
class Tenant:
    slug: str
    tenant_id: str
    owner: Member
    members: dict[str, Member] = field(default_factory=dict)

    def h(self, role: str = "owner") -> dict[str, str]:
        member = self.owner if role == "owner" else self.members[role]
        return member.headers(self.slug)


def login(backend: httpx.Client, email: str) -> str:
    response = backend.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def provision(backend: httpx.Client, label: str) -> Tenant:
    slug = f"bnd-{label}-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@boundary.example"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.provision_tenant",
            "--name",
            f"Boundary {label}",
            "--slug",
            slug,
            "--owner-email",
            email,
            "--owner-password-stdin",
        ],
        input=PASSWORD + "\n",
        capture_output=True,
        text=True,
        cwd="/app",
        env={**os.environ, "APP_ENVIRONMENT": "development"},
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    token = login(backend, email)
    memberships = backend.get("/identity/memberships", headers={"Authorization": f"Bearer {token}"})
    entry = next(m for m in memberships.json()["data"] if m["tenant_slug"] == slug)
    me = backend.get("/identity/me", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    owner = Member(email, me["id"], token, "owner", entry.get("membership_id", entry.get("id", "")))
    return Tenant(slug=slug, tenant_id=entry["tenant_id"], owner=owner)


def invite(backend: httpx.Client, tenant: Tenant, role: str) -> Member:
    email = f"{role}-{uuid.uuid4().hex[:8]}@boundary.example"
    mark = len(OUTBOX.read_text(encoding="utf-8").splitlines()) if OUTBOX.exists() else 0
    created = backend.post(
        f"/tenants/{tenant.slug}/invitations",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {tenant.owner.token}"},
    )
    assert created.status_code == 201, created.text
    invitation_code = outbox_code(email, "You have been invited", mark)

    registered = backend.post("/identity/users", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201, registered.text
    verified = backend.post("/identity/verify-email", json={"token": outbox_code(email, "Verify your BUILD", mark)})
    assert verified.status_code == 200, verified.text
    token = login(backend, email)
    accepted = backend.post("/invitations/accept", json={"token": invitation_code}, headers={"Authorization": f"Bearer {token}"})
    assert accepted.status_code == 200, accepted.text
    data = accepted.json()["data"]
    member = Member(email, registered.json()["data"]["id"], token, role, data["membership_id"])
    tenant.members[role] = member
    return member


@pytest.fixture(scope="session")
def tenant_a(backend: httpx.Client) -> Tenant:
    tenant = provision(backend, "a")
    invite(backend, tenant, "lecturer")
    invite(backend, tenant, "student")
    return tenant


@pytest.fixture(scope="session")
def tenant_b(backend: httpx.Client) -> Tenant:
    tenant = provision(backend, "b")
    invite(backend, tenant, "lecturer")
    return tenant


# --- Content ---------------------------------------------------------------------------


def pdf_document(marker: str | None = None) -> bytes:
    """A valid one-page PDF with a real text layer, unique per call
    (duplicate content is tenant-wide). The AI-service extracts it (P3-2),
    so it must be a PDF a reader can open, not just bytes that start with
    %PDF-. Built here with correct offsets; no PDF library needed. The
    "Reference <marker>" line identifies the document in retrieval tests."""
    marker = marker or uuid.uuid4().hex
    lines = [
        "BUILD boundary gate document",
        f"Reference {marker}",
        "Electric charge is conserved: in every interaction the total charge",
        "before equals the total charge after. Like charges repel and unlike",
        "charges attract, with a force that falls with the square of distance.",
    ]
    text = "BT /F1 12 Tf 72 720 Td 16 TL " + " ".join(f"({line}) '" for line in lines) + " ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(text), text.encode("latin-1")),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def create_source(backend: httpx.Client, tenant: Tenant) -> str:
    source = backend.post(
        "/content/sources",
        json={
            "code": f"BND_{uuid.uuid4().hex[:8].upper()}",
            "name": "Boundary",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=tenant.h("lecturer"),
    )
    assert source.status_code == 201, source.text
    return source.json()["data"]["id"]


def upload(backend: httpx.Client, tenant: Tenant, source_id: str, document: bytes) -> httpx.Response:
    return backend.post(
        f"/content/sources/{source_id}/assets/upload",
        params={"file_name": "boundary.pdf"},
        content=document,
        headers=tenant.h("lecturer")
        | {"Idempotency-Key": f"boundary-{uuid.uuid4().hex}", "Content-Type": "application/octet-stream"},
    )


def create_asset(backend: httpx.Client, tenant: Tenant, document: bytes | None = None) -> dict[str, Any]:
    """An asset created the only way there is (P3-1 PR 3b): real bytes
    uploaded to the stack's object storage."""
    document = document if document is not None else pdf_document()
    response = upload(backend, tenant, create_source(backend, tenant), document)
    assert response.status_code == 201, response.text
    stored = response.json()["data"]
    assert stored["content_sha256"] == hashlib.sha256(document).hexdigest()
    assert stored["storage_uri"].startswith("s3://build-documents/tenants/")
    return stored


def create_job_for(backend: httpx.Client, tenant: Tenant, asset: dict[str, Any]) -> dict[str, Any]:
    job = backend.post(f"/content/assets/{asset['id']}/jobs", json={"max_attempts": 3}, headers=tenant.h("lecturer"))
    assert job.status_code == 201, job.text
    return job.json()["data"]


def create_job(backend: httpx.Client, tenant: Tenant) -> dict[str, Any]:
    return create_job_for(backend, tenant, create_asset(backend, tenant))


def pipeline_outcome(job: dict[str, Any]) -> dict[str, Any]:
    """The end of a valid document's ingestion, returning its fetch evidence.

    A valid document ends ready (P3-4), with the evidence the backend's
    stage contract requires: every chunk durably indexed in
    document_chunks, the extraction method and characters, and the
    verified fetch.
    """
    assert job["status"] == "ready", job
    metrics = job["metrics"]
    assert metrics["indexed_chunks"] == metrics["chunks"] >= 1, metrics
    assert metrics["index"] == "document_chunks", metrics
    assert metrics["method"] in ("native_text", "ocr") and metrics["characters"] >= 1, metrics
    return metrics["chunk_summary"]["fetch"]


def object_store():
    """The stack's object store with the backend's identity (read, write,
    list), for tests that tamper with or delete what an upload stored."""
    import boto3
    from botocore.config import Config

    return boto3.session.Session().client(
        "s3",
        endpoint_url=os.environ["BOUNDARY_STORAGE_ENDPOINT"],
        region_name="us-east-1",
        aws_access_key_id=os.environ["BOUNDARY_STORAGE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["BOUNDARY_STORAGE_SECRET_KEY"],
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 2},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def object_key(asset: dict[str, Any]) -> str:
    return asset["storage_uri"].split("/", 3)[3]


def get_job(backend: httpx.Client, tenant: Tenant, job_id: str) -> dict[str, Any]:
    response = backend.get(f"/content/jobs/{job_id}", headers=tenant.h("lecturer"))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def wait_for_status(backend, tenant, job_id, statuses: set[str], timeout: float = 60) -> dict[str, Any]:
    deadline = time.time() + timeout
    job = get_job(backend, tenant, job_id)
    while job["status"] not in statuses and time.time() < deadline:
        time.sleep(0.5)
        job = get_job(backend, tenant, job_id)
    return job
