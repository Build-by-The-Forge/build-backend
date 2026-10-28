from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.domain.content.asset import ContentAsset
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource


@dataclass(frozen=True, slots=True)
class AIServiceDispatchResult:
    external_task_id: str
    accepted_at: datetime
    status: str
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIServiceStatusResult:
    """AI-service's account of one task (M3-09): its attempt identity, state,
    and the exact callback bodies it produced, in order. The backend applies
    those events through its callback rules; it never trusts ``state``
    alone."""

    external_task_id: str
    job_id: str
    run_number: int
    attempt_count: int
    state: str
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IngestionDispatchActor:
    """Who is dispatching, as resolved and authorized by the backend. It
    becomes the signed user context; AI-service learns the tenant only
    from it (design B.2)."""

    tenant_id: str
    user_id: str
    membership_id: str
    role: str
    permission: str


@dataclass(frozen=True, slots=True)
class SystemDispatchActor:
    """The backend's ingestion worker delivering a job that an authorized
    user already created (P3-6 §9). It becomes a signed system context: no
    user, no permissions, and the job's own tenant, the only tenant it may
    name."""

    tenant_id: str

    @classmethod
    def for_job(cls, job: ContentIngestionJob) -> SystemDispatchActor:
        if not job.tenant_id:
            raise JobTenantMissing(f"job {job.id} has no tenant; the worker cannot dispatch it")
        return cls(tenant_id=job.tenant_id)


class JobTenantMissing(Exception):
    """A job without a tenant cannot be dispatched by the worker: the system
    context must name the job's own tenant, and there is none to name."""

    error_code = "JOB_TENANT_MISSING"
    is_retryable = False


class AIServiceIngestionGateway(Protocol):
    async def dispatch_ingestion_job(
        self,
        job: ContentIngestionJob,
        asset: ContentAsset,
        source: ContentSource,
        actor: IngestionDispatchActor | SystemDispatchActor,
    ) -> AIServiceDispatchResult:
        raise NotImplementedError

    async def fetch_job_status(self, external_task_id: str, tenant_id: str, correlation_id: str) -> AIServiceStatusResult:
        raise NotImplementedError
