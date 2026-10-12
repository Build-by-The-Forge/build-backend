from __future__ import annotations

from typing import Any

from app.application.common.uow import ContentUnitOfWorkFactory
from app.application.content.source_commands import (
    ActivateContentSourceCommand,
    DeprecateContentSourceCommand,
    GetContentSourceQuery,
    ListContentSourcesQuery,
    RegisterContentSourceCommand,
    RevokeContentSourceCommand,
    UpdateContentSourceCommand,
)
from app.application.content.source_handlers import (
    ActivateContentSourceHandler,
    DeprecateContentSourceHandler,
    GetContentSourceHandler,
    ListContentSourcesHandler,
    RegisterContentSourceHandler,
    RevokeContentSourceHandler,
    UpdateContentSourceHandler,
)
from app.domain.content.source import ContentSource
from app.domain.repositories.content_source import ContentSourceRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class ContentSourceService:
    def __init__(
        self,
        repository: ContentSourceRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: ContentUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def register_source(
        self,
        code: str,
        name: str,
        source_type: str,
        authority_level: str,
        visibility: str,
        created_by: str,
        created_by_email: str,
        tenant_id: str | None = None,
        faculty_id: str | None = None,
        department_id: str | None = None,
        programme_id: str | None = None,
        description: str | None = None,
        author_name: str | None = None,
        publisher: str | None = None,
        isbn_or_doi: str | None = None,
        source_url: str | None = None,
        trust_policy: dict[str, Any] | None = None,
    ) -> ContentSource:
        command = RegisterContentSourceCommand(
            code=code,
            name=name,
            source_type=source_type,
            authority_level=authority_level,
            visibility=visibility,
            created_by=created_by,
            created_by_email=created_by_email,
            tenant_id=tenant_id,
            faculty_id=faculty_id,
            department_id=department_id,
            programme_id=programme_id,
            description=description,
            author_name=author_name,
            publisher=publisher,
            isbn_or_doi=isbn_or_doi,
            source_url=source_url,
            trust_policy=trust_policy or {},
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                source = await RegisterContentSourceHandler(uow.sources, self.event_bus).handle(command)
                events = source.pull_events()
            self._publish_events(events)
            return source

        source = await RegisterContentSourceHandler(self._required_repository(), self.event_bus).handle(command)
        self._publish_events(source.pull_events())
        return source

    async def update_source(
        self,
        source_id: str,
        name: str | None = None,
        description: str | None = None,
        author_name: str | None = None,
        publisher: str | None = None,
        isbn_or_doi: str | None = None,
        source_url: str | None = None,
        trust_policy: dict[str, Any] | None = None,
    ) -> ContentSource:
        command = UpdateContentSourceCommand(
            source_id=source_id,
            name=name,
            description=description,
            author_name=author_name,
            publisher=publisher,
            isbn_or_doi=isbn_or_doi,
            source_url=source_url,
            trust_policy=trust_policy,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                source = await UpdateContentSourceHandler(uow.sources, self.event_bus).handle(command)
                events = source.pull_events()
            self._publish_events(events)
            return source

        source = await UpdateContentSourceHandler(self._required_repository(), self.event_bus).handle(command)
        self._publish_events(source.pull_events())
        return source

    async def deprecate_source(self, source_id: str, reason: str) -> ContentSource:
        command = DeprecateContentSourceCommand(source_id=source_id, reason=reason)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                source = await DeprecateContentSourceHandler(uow.sources, self.event_bus).handle(command)
                events = source.pull_events()
            self._publish_events(events)
            return source

        source = await DeprecateContentSourceHandler(self._required_repository(), self.event_bus).handle(command)
        self._publish_events(source.pull_events())
        return source

    async def revoke_source(self, source_id: str, reason: str) -> ContentSource:
        command = RevokeContentSourceCommand(source_id=source_id, reason=reason)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                source = await RevokeContentSourceHandler(uow.sources, self.event_bus).handle(command)
                events = source.pull_events()
            self._publish_events(events)
            return source

        source = await RevokeContentSourceHandler(self._required_repository(), self.event_bus).handle(command)
        self._publish_events(source.pull_events())
        return source

    async def activate_source(self, source_id: str) -> ContentSource:
        command = ActivateContentSourceCommand(source_id=source_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                source = await ActivateContentSourceHandler(uow.sources, self.event_bus).handle(command)
                events = source.pull_events()
            self._publish_events(events)
            return source

        source = await ActivateContentSourceHandler(self._required_repository(), self.event_bus).handle(command)
        self._publish_events(source.pull_events())
        return source

    async def get_source(self, source_id: str) -> ContentSource | None:
        query = GetContentSourceQuery(source_id=source_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetContentSourceHandler(uow.sources).handle(query)
        return await GetContentSourceHandler(self._required_repository()).handle(query)

    async def list_sources(
        self,
        tenant_id: str | None = None,
        source_type: str | None = None,
        authority_level: str | None = None,
        status: str | None = None,
        include_platform: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentSource], int]:
        query = ListContentSourcesQuery(
            tenant_id=tenant_id,
            source_type=source_type,
            authority_level=authority_level,
            status=status,
            include_platform=include_platform,
            limit=limit,
            offset=offset,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListContentSourcesHandler(uow.sources).handle(query)
        return await ListContentSourcesHandler(self._required_repository()).handle(query)

    def _required_repository(self) -> ContentSourceRepository:
        if self.repository is None:
            raise ValueError("content source repository is required")
        return self.repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None and events:
            self.event_bus.publish_all(events)
