from __future__ import annotations

from typing import Protocol

from app.domain.content.enums import IngestionStatus
from app.domain.content.job import ContentIngestionJob


class ContentIngestionJobRepository(Protocol):
    async def save_job(self, job: ContentIngestionJob) -> ContentIngestionJob:
        raise NotImplementedError

    async def get_job_by_id(self, job_id: str) -> ContentIngestionJob | None:
        raise NotImplementedError

    async def get_latest_job_for_asset(
        self, asset_id: str
    ) -> ContentIngestionJob | None:
        raise NotImplementedError

    async def list_jobs_for_asset(
        self, asset_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ContentIngestionJob], int]:
        raise NotImplementedError

    async def list_pending_jobs(
        self, tenant_id: str | None = None, limit: int = 50
    ) -> list[ContentIngestionJob]:
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
