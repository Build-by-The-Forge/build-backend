from __future__ import annotations

from typing import Protocol

from app.domain.content.enums import AuthorityLevel, ContentSourceType, SourceStatus
from app.domain.content.source import ContentSource


class ContentSourceRepository(Protocol):
    async def save_source(self, source: ContentSource) -> ContentSource:
        raise NotImplementedError

    async def get_source_by_id(self, source_id: str) -> ContentSource | None:
        raise NotImplementedError

    async def get_source_by_code(
        self, code: str, tenant_id: str | None = None
    ) -> ContentSource | None:
        raise NotImplementedError

    async def list_sources(
        self,
        tenant_id: str | None = None,
        source_type: ContentSourceType | None = None,
        authority_level: AuthorityLevel | None = None,
        status: SourceStatus | None = None,
        include_platform: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentSource], int]:
        raise NotImplementedError
