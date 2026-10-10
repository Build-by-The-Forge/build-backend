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
    external_task_id: str
    status: str
    stage: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    is_retryable: bool = False


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


class AIServiceIngestionGateway(Protocol):
    async def dispatch_ingestion_job(
        self,
        job: ContentIngestionJob,
        asset: ContentAsset,
        source: ContentSource,
        actor: IngestionDispatchActor,
    ) -> AIServiceDispatchResult:
        raise NotImplementedError

    async def fetch_job_status(
        self, external_task_id: str
    ) -> AIServiceStatusResult:
        raise NotImplementedError
