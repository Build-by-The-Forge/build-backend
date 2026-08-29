from typing import Protocol

from app.domain.curriculum.audit import BenchmarkAuditLog


class BenchmarkAuditRepository(Protocol):
    async def save(self, log: BenchmarkAuditLog) -> BenchmarkAuditLog:
        raise NotImplementedError

    async def list_by_curriculum(self, curriculum_id: str) -> list[BenchmarkAuditLog]:
        raise NotImplementedError

    async def list_recent(
        self, limit: int = 50, action: str | None = None
    ) -> list[BenchmarkAuditLog]:
        raise NotImplementedError
