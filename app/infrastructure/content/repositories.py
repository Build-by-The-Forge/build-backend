from __future__ import annotations

from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
    VisibilityScope,
)
from app.domain.content.source import ContentSource
from app.domain.repositories.content_source import ContentSourceRepository
from app.infrastructure.content.mappers import (
    content_source_model_to_domain,
    content_source_to_model,
)
from app.infrastructure.db.models.content import ContentSourceModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyContentSourceRepository(ContentSourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_source(self, source: ContentSource) -> ContentSource:
        statement = select(ContentSourceModel).where(ContentSourceModel.id == source.id)
        model = (await self._session.scalars(statement)).first()
        if model is None:
            model = content_source_to_model(source)
            self._session.add(model)
        else:
            content_source_to_model(source, model=model)
        await self._session.flush()
        return source

    async def get_source_by_id(self, source_id: str) -> ContentSource | None:
        statement = select(ContentSourceModel).where(ContentSourceModel.id == source_id)
        model = (await self._session.scalars(statement)).first()
        return content_source_model_to_domain(model) if model is not None else None

    async def get_source_by_code(self, code: str, tenant_id: str | None = None) -> ContentSource | None:
        statement = select(ContentSourceModel).where(ContentSourceModel.code == code.upper())
        if tenant_id is not None:
            statement = statement.where(
                or_(
                    ContentSourceModel.tenant_id == tenant_id,
                    ContentSourceModel.visibility == VisibilityScope.PLATFORM.value,
                )
            )
        else:
            statement = statement.where(ContentSourceModel.visibility == VisibilityScope.PLATFORM.value)
        model = (await self._session.scalars(statement)).first()
        return content_source_model_to_domain(model) if model is not None else None

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
        base_query = select(ContentSourceModel)

        conditions = []
        if tenant_id is not None:
            if include_platform:
                conditions.append(
                    or_(
                        ContentSourceModel.tenant_id == tenant_id,
                        ContentSourceModel.visibility == VisibilityScope.PLATFORM.value,
                    )
                )
            else:
                conditions.append(ContentSourceModel.tenant_id == tenant_id)
        elif not include_platform:
            conditions.append(ContentSourceModel.tenant_id.is_(None))

        if source_type is not None:
            conditions.append(ContentSourceModel.source_type == source_type.value)
        if authority_level is not None:
            conditions.append(ContentSourceModel.authority_level == authority_level.value)
        if status is not None:
            conditions.append(ContentSourceModel.status == status.value)

        for condition in conditions:
            base_query = base_query.where(condition)

        count_query = select(func.count()).select_from(base_query.subquery())
        total_count = (await self._session.scalar(count_query)) or 0

        paginated_query = base_query.order_by(ContentSourceModel.code.asc()).limit(limit).offset(offset)
        models = (await self._session.scalars(paginated_query)).all()
        return [content_source_model_to_domain(m) for m in models], total_count
