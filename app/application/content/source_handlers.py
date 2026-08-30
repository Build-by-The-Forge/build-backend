from __future__ import annotations

from app.application.content.source_commands import (
    ActivateContentSourceCommand,
    DeprecateContentSourceCommand,
    GetContentSourceQuery,
    ListContentSourcesQuery,
    RegisterContentSourceCommand,
    RevokeContentSourceCommand,
    UpdateContentSourceCommand,
)
from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
)
from app.domain.content.source import ContentSource
from app.domain.repositories.content_source import ContentSourceRepository
from app.events.event_bus import EventBus


class RegisterContentSourceHandler:
    def __init__(
        self, repository: ContentSourceRepository, event_bus: EventBus | None = None
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def handle(self, command: RegisterContentSourceCommand) -> ContentSource:
        clean_code = command.code.strip().upper()
        existing = await self.repository.get_source_by_code(
            clean_code, command.tenant_id
        )
        if existing is not None:
            raise ValueError(
                f"content source with code '{clean_code}' already exists in this scope"
            )

        source = ContentSource.create(
            code=clean_code,
            name=command.name,
            source_type=command.source_type,
            authority_level=command.authority_level,
            visibility=command.visibility,
            created_by=command.created_by,
            created_by_email=command.created_by_email,
            tenant_id=command.tenant_id,
            faculty_id=command.faculty_id,
            department_id=command.department_id,
            programme_id=command.programme_id,
            description=command.description,
            author_name=command.author_name,
            publisher=command.publisher,
            isbn_or_doi=command.isbn_or_doi,
            source_url=command.source_url,
            trust_policy=command.trust_policy,
        )

        saved = await self.repository.save_source(source)
        events = source.pull_events()
        if self.event_bus and events:
            self.event_bus.publish_all(events)
        return saved


class UpdateContentSourceHandler:
    def __init__(
        self, repository: ContentSourceRepository, event_bus: EventBus | None = None
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def handle(self, command: UpdateContentSourceCommand) -> ContentSource:
        source = await self.repository.get_source_by_id(command.source_id)
        if source is None:
            raise ValueError(f"content source '{command.source_id}' not found")

        source.update_metadata(
            name=command.name,
            description=command.description,
            author_name=command.author_name,
            publisher=command.publisher,
            isbn_or_doi=command.isbn_or_doi,
            source_url=command.source_url,
            trust_policy=command.trust_policy,
        )

        saved = await self.repository.save_source(source)
        events = source.pull_events()
        if self.event_bus and events:
            self.event_bus.publish_all(events)
        return saved


class DeprecateContentSourceHandler:
    def __init__(
        self, repository: ContentSourceRepository, event_bus: EventBus | None = None
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def handle(self, command: DeprecateContentSourceCommand) -> ContentSource:
        source = await self.repository.get_source_by_id(command.source_id)
        if source is None:
            raise ValueError(f"content source '{command.source_id}' not found")

        source.deprecate(command.reason)
        saved = await self.repository.save_source(source)
        events = source.pull_events()
        if self.event_bus and events:
            self.event_bus.publish_all(events)
        return saved


class RevokeContentSourceHandler:
    def __init__(
        self, repository: ContentSourceRepository, event_bus: EventBus | None = None
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def handle(self, command: RevokeContentSourceCommand) -> ContentSource:
        source = await self.repository.get_source_by_id(command.source_id)
        if source is None:
            raise ValueError(f"content source '{command.source_id}' not found")

        source.revoke(command.reason)
        saved = await self.repository.save_source(source)
        events = source.pull_events()
        if self.event_bus and events:
            self.event_bus.publish_all(events)
        return saved


class ActivateContentSourceHandler:
    def __init__(
        self, repository: ContentSourceRepository, event_bus: EventBus | None = None
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def handle(self, command: ActivateContentSourceCommand) -> ContentSource:
        source = await self.repository.get_source_by_id(command.source_id)
        if source is None:
            raise ValueError(f"content source '{command.source_id}' not found")

        source.activate()
        saved = await self.repository.save_source(source)
        events = source.pull_events()
        if self.event_bus and events:
            self.event_bus.publish_all(events)
        return saved


class GetContentSourceHandler:
    def __init__(self, repository: ContentSourceRepository) -> None:
        self.repository = repository

    async def handle(self, query: GetContentSourceQuery) -> ContentSource | None:
        return await self.repository.get_source_by_id(query.source_id)


class ListContentSourcesHandler:
    def __init__(self, repository: ContentSourceRepository) -> None:
        self.repository = repository

    async def handle(
        self, query: ListContentSourcesQuery
    ) -> tuple[list[ContentSource], int]:
        st = (
            ContentSourceType(query.source_type)
            if isinstance(query.source_type, str)
            else query.source_type
        )
        al = (
            AuthorityLevel(query.authority_level)
            if isinstance(query.authority_level, str)
            else query.authority_level
        )
        status = (
            SourceStatus(query.status)
            if isinstance(query.status, str)
            else query.status
        )

        return await self.repository.list_sources(
            tenant_id=query.tenant_id,
            source_type=st,
            authority_level=al,
            status=status,
            include_platform=query.include_platform,
            limit=query.limit,
            offset=query.offset,
        )
