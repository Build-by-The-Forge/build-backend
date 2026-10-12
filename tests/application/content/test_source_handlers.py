import pytest
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
from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
    VisibilityScope,
)
from app.domain.content.source import ContentSource
from app.domain.repositories.content_source import ContentSourceRepository
from app.events.event_bus import EventBus


class InMemoryContentSourceRepository(ContentSourceRepository):
    def __init__(self) -> None:
        self.sources: dict[str, ContentSource] = {}

    async def save_source(self, source: ContentSource) -> ContentSource:
        self.sources[source.id] = source
        return source

    async def get_source_by_id(self, source_id: str) -> ContentSource | None:
        return self.sources.get(source_id)

    async def get_source_by_code(self, code: str, tenant_id: str | None = None) -> ContentSource | None:
        for s in self.sources.values():
            if s.code == code.upper():
                if tenant_id is not None:
                    if s.tenant_id == tenant_id or s.visibility == VisibilityScope.PLATFORM:
                        return s
                else:
                    if s.visibility == VisibilityScope.PLATFORM:
                        return s
        return None

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
        results: list[ContentSource] = []
        for s in self.sources.values():
            if tenant_id is not None:
                if include_platform:
                    if s.tenant_id != tenant_id and s.visibility != VisibilityScope.PLATFORM:
                        continue
                else:
                    if s.tenant_id != tenant_id:
                        continue
            elif not include_platform:
                if s.tenant_id is not None:
                    continue

            if source_type and s.source_type != source_type:
                continue
            if authority_level and s.authority_level != authority_level:
                continue
            if status and s.status != status:
                continue
            results.append(s)

        results.sort(key=lambda x: x.code)
        total = len(results)
        return results[offset : offset + limit], total


@pytest.mark.asyncio
async def test_register_content_source_handler_success() -> None:
    repo = InMemoryContentSourceRepository()
    event_bus = EventBus()
    published_events = []
    event_bus.subscribe("content.source_created", lambda e: published_events.append(e))

    handler = RegisterContentSourceHandler(repository=repo, event_bus=event_bus)

    cmd = RegisterContentSourceCommand(
        code="NUC_CCMAS",
        name="CCMAS National Curriculum",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-admin",
        created_by_email="admin@nuc.ng",
    )
    source = await handler.handle(cmd)

    assert source.code == "NUC_CCMAS"
    assert source.id in repo.sources
    assert len(published_events) == 1
    assert published_events[0].payload["code"] == "NUC_CCMAS"


@pytest.mark.asyncio
async def test_register_content_source_duplicate_code_fails() -> None:
    repo = InMemoryContentSourceRepository()
    handler = RegisterContentSourceHandler(repository=repo)

    cmd1 = RegisterContentSourceCommand(
        code="CSC101_NOTES",
        name="CSC101 Notes",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
        tenant_id="tenant-futa",
    )
    await handler.handle(cmd1)

    # Attempt duplicate registration with same code and tenant
    cmd2 = RegisterContentSourceCommand(
        code="csc101_notes",
        name="CSC101 Notes Duplicate",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-lecturer-2",
        created_by_email="lecturer2@futa.edu.ng",
        tenant_id="tenant-futa",
    )

    with pytest.raises(ValueError, match="already exists in this scope"):
        await handler.handle(cmd2)


@pytest.mark.asyncio
async def test_update_and_lifecycle_handlers() -> None:
    repo = InMemoryContentSourceRepository()
    event_bus = EventBus()
    published_events = []
    event_bus.subscribe("content.source_updated", lambda e: published_events.append(e))
    event_bus.subscribe("content.source_deprecated", lambda e: published_events.append(e))
    event_bus.subscribe("content.source_revoked", lambda e: published_events.append(e))
    event_bus.subscribe("content.source_activated", lambda e: published_events.append(e))

    reg_handler = RegisterContentSourceHandler(repo, event_bus)
    update_handler = UpdateContentSourceHandler(repo, event_bus)
    dep_handler = DeprecateContentSourceHandler(repo, event_bus)
    rev_handler = RevokeContentSourceHandler(repo, event_bus)
    act_handler = ActivateContentSourceHandler(repo, event_bus)
    get_handler = GetContentSourceHandler(repo)

    source = await reg_handler.handle(
        RegisterContentSourceCommand(
            code="TEXT_01",
            name="Original Textbook",
            source_type=ContentSourceType.TEXTBOOK,
            authority_level=AuthorityLevel.APPROVED_REFERENCE,
            visibility=VisibilityScope.TENANT,
            created_by="admin",
            created_by_email="admin@futa.ng",
            tenant_id="tenant-futa",
        )
    )

    # Update
    updated = await update_handler.handle(
        UpdateContentSourceCommand(
            source_id=source.id,
            name="Updated Textbook Name",
            author_name="Author Person",
        )
    )
    assert updated.name == "Updated Textbook Name"
    assert updated.author_name == "Author Person"

    # Deprecate
    dep = await dep_handler.handle(DeprecateContentSourceCommand(source_id=source.id, reason="Old edition"))
    assert dep.status == SourceStatus.DEPRECATED

    # Reactivate
    act = await act_handler.handle(ActivateContentSourceCommand(source_id=source.id))
    assert act.status == SourceStatus.ACTIVE

    # Revoke
    rev = await rev_handler.handle(RevokeContentSourceCommand(source_id=source.id, reason="Invalid license"))
    assert rev.status == SourceStatus.REVOKED

    # Get
    fetched = await get_handler.handle(GetContentSourceQuery(source_id=source.id))
    assert fetched is not None
    assert fetched.status == SourceStatus.REVOKED


@pytest.mark.asyncio
async def test_list_content_sources_handler() -> None:
    repo = InMemoryContentSourceRepository()
    reg_handler = RegisterContentSourceHandler(repo)
    list_handler = ListContentSourcesHandler(repo)

    # Add 1 platform source and 2 tenant-futa sources
    await reg_handler.handle(
        RegisterContentSourceCommand(
            code="CCMAS",
            name="CCMAS",
            source_type=ContentSourceType.CCMAS,
            authority_level=AuthorityLevel.REGULATORY,
            visibility=VisibilityScope.PLATFORM,
            created_by="admin",
            created_by_email="admin@nuc.ng",
        )
    )
    await reg_handler.handle(
        RegisterContentSourceCommand(
            code="FUTA_CSC",
            name="FUTA CSC",
            source_type=ContentSourceType.LECTURER_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.TENANT,
            created_by="admin",
            created_by_email="admin@futa.ng",
            tenant_id="tenant-futa",
        )
    )
    await reg_handler.handle(
        RegisterContentSourceCommand(
            code="UNILAG_CSC",
            name="UNILAG CSC",
            source_type=ContentSourceType.LECTURER_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.TENANT,
            created_by="admin",
            created_by_email="admin@unilag.ng",
            tenant_id="tenant-unilag",
        )
    )

    # Query from FUTA perspective (should see CCMAS + FUTA_CSC)
    items, total = await list_handler.handle(ListContentSourcesQuery(tenant_id="tenant-futa", include_platform=True))
    codes = [s.code for s in items]
    assert total == 2
    assert "CCMAS" in codes
    assert "FUTA_CSC" in codes
    assert "UNILAG_CSC" not in codes
