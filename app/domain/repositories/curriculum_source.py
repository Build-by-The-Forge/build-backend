from typing import Protocol

from app.domain.curriculum.source import CurriculumSnapshot, CurriculumSource


class CurriculumSourceRepository(Protocol):
    async def save_source(self, source: CurriculumSource) -> CurriculumSource:
        raise NotImplementedError

    async def get_source_by_id(self, source_id: str) -> CurriculumSource | None:
        raise NotImplementedError

    async def get_source_by_code(self, code: str) -> CurriculumSource | None:
        raise NotImplementedError

    async def list_sources(self, status: str | None = None) -> list[CurriculumSource]:
        raise NotImplementedError

    async def save_snapshot(self, snapshot: CurriculumSnapshot) -> CurriculumSnapshot:
        raise NotImplementedError

    async def get_latest_snapshot(self, source_id: str) -> CurriculumSnapshot | None:
        raise NotImplementedError

    async def get_snapshot_by_hash(self, source_id: str, content_sha256: str) -> CurriculumSnapshot | None:
        raise NotImplementedError

    async def list_snapshots(self, source_id: str, limit: int = 50, offset: int = 0) -> tuple[list[CurriculumSnapshot], int]:
        raise NotImplementedError
