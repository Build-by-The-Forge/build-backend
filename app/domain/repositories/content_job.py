from __future__ import annotations

from typing import Protocol

from app.domain.content.enums import IngestionStatus
from app.domain.content.ingestion_event import IngestionEventRecord
from app.domain.content.job import ContentIngestionJob


class ContentIngestionJobRepository(Protocol):
    async def save_job(self, job: ContentIngestionJob) -> ContentIngestionJob:
        raise NotImplementedError

    async def get_job_by_id(self, job_id: str) -> ContentIngestionJob | None:
        raise NotImplementedError

    async def get_job_for_update(self, job_id: str) -> ContentIngestionJob | None:
        """Load the job and lock its row until the unit of work ends, so
        competing callbacks for one job are applied one at a time."""
        raise NotImplementedError

    async def get_latest_job_for_asset(self, asset_id: str) -> ContentIngestionJob | None:
        raise NotImplementedError

    async def list_jobs_for_asset(self, asset_id: str, limit: int = 50, offset: int = 0) -> tuple[list[ContentIngestionJob], int]:
        raise NotImplementedError

    async def list_pending_jobs(self, tenant_id: str | None = None, limit: int = 50) -> list[ContentIngestionJob]:
        raise NotImplementedError

    async def claim_next_due_dispatch(self, excluded_ids: set[str], claim_seconds: int = 120) -> ContentIngestionJob | None:
        """Lock and return one due queued job with an expiring durable claim."""
        raise NotImplementedError

    async def claim_next_retryable_failure(self, excluded_ids: set[str]) -> ContentIngestionJob | None:
        """Lock and return exactly one oldest retryable failure below its cap."""
        raise NotImplementedError

    async def list_jobs(
        self,
        tenant_id: str | None = None,
        asset_id: str | None = None,
        source_id: str | None = None,
        status: IngestionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentIngestionJob], int]:
        raise NotImplementedError


class IngestionEventRepository(Protocol):
    async def get(self, event_id: str) -> IngestionEventRecord | None:
        raise NotImplementedError

    async def add(self, record: IngestionEventRecord) -> None:
        raise NotImplementedError
