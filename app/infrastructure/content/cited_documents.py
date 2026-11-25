"""The backend's own record of a cited document: its source and its title.

A tutor answer's citations come from AI-service, which knows a document by its
ID and version. What a student is shown about the document (its source and its
display name) is never the model's or AI-service's: it is read here, from the
backend's records, and only within the caller's tenant.
"""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.content import ContentAssetModel


async def cited_documents(tenant_id: str, asset_ids: set[str]) -> dict[str, tuple[str, str]]:
    """``{asset_id: (source_id, title)}`` for the tenant's own documents among
    ``asset_ids``. A document of another tenant, or an unknown ID, is absent.
    Whether the caller may read it is the read policy's question, asked by the
    provenance check; this only supplies what is shown."""
    if not asset_ids:
        return {}
    async with SessionLocal() as session:
        rows = await session.execute(
            select(ContentAssetModel.id, ContentAssetModel.source_id, ContentAssetModel.file_name).where(
                ContentAssetModel.tenant_id == tenant_id, ContentAssetModel.id.in_(asset_ids)
            )
        )
        return {asset_id: (source_id, file_name) for asset_id, source_id, file_name in rows}
