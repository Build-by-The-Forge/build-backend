"""Reads of content_blobs (M3-D)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.content.blob import ContentBlob
from app.infrastructure.db.models.content import ContentBlobModel


class SqlAlchemyBlobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: str, blob_id: str) -> ContentBlob | None:
        """The tenant's blob, or None: another tenant's row is never returned."""
        statement = select(ContentBlobModel).where(ContentBlobModel.id == blob_id, ContentBlobModel.tenant_id == tenant_id)
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        return ContentBlob(
            id=model.id,
            tenant_id=model.tenant_id,
            content_sha256=model.content_sha256,
            generation=model.generation,
            object_key=model.object_key,
            state=model.state,
        )
