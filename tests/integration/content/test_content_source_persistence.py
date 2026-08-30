import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
    VisibilityScope,
)
from app.domain.content.source import ContentSource
from app.infrastructure.content.repositories import SqlAlchemyContentSourceRepository


@pytest.mark.asyncio
async def test_content_source_persistence_round_trip(session: AsyncSession) -> None:
    repository = SqlAlchemyContentSourceRepository(session)

    source = ContentSource.create(
        code="NUC_CCMAS_CS_TEST",
        name="NUC CCMAS CS Test",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-admin",
        created_by_email="admin@nuc.ng",
        author_name="NUC Board",
        description="Benchmark CS curriculum",
        source_url="https://ccmas.nuc.edu.ng/cs",
        trust_policy={"auto_index": True, "priority": "high"},
    )
    await repository.save_source(source)

    # Lookup by ID
    retrieved = await repository.get_source_by_id(source.id)
    assert retrieved is not None
    assert retrieved.id == source.id
    assert retrieved.code == "NUC_CCMAS_CS_TEST"
    assert retrieved.name == "NUC CCMAS CS Test"
    assert retrieved.source_type == ContentSourceType.CCMAS
    assert retrieved.authority_level == AuthorityLevel.REGULATORY
    assert retrieved.visibility == VisibilityScope.PLATFORM
    assert retrieved.status == SourceStatus.ACTIVE
    assert retrieved.trust_policy == {"auto_index": True, "priority": "high"}

    # Lookup by Code
    by_code = await repository.get_source_by_code("nuc_ccmas_cs_test")
    assert by_code is not None
    assert by_code.id == source.id

    # List
    sources, total = await repository.list_sources()
    assert total >= 1
    assert any(s.code == "NUC_CCMAS_CS_TEST" for s in sources)


@pytest.mark.asyncio
async def test_content_source_tenant_isolation_persistence(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyContentSourceRepository(session)

    # 1. Platform source
    plat_source = ContentSource.create(
        code="PLAT_SRC_1",
        name="Platform Source",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="admin",
        created_by_email="admin@nuc.ng",
    )
    await repository.save_source(plat_source)

    # 2. FUTA institutional source
    futa_source = ContentSource.create(
        code="FUTA_SRC_1",
        name="FUTA Notes",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="lecturer",
        created_by_email="lecturer@futa.edu.ng",
        tenant_id="tenant-futa",
    )
    await repository.save_source(futa_source)

    # 3. UNILAG institutional source
    unilag_source = ContentSource.create(
        code="UNILAG_SRC_1",
        name="UNILAG Notes",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="lecturer",
        created_by_email="lecturer@unilag.edu.ng",
        tenant_id="tenant-unilag",
    )
    await repository.save_source(unilag_source)

    # List from FUTA tenant context (should include Platform + FUTA, but NOT UNILAG)
    futa_list, futa_total = await repository.list_sources(
        tenant_id="tenant-futa", include_platform=True
    )
    futa_codes = {s.code for s in futa_list}
    assert "PLAT_SRC_1" in futa_codes
    assert "FUTA_SRC_1" in futa_codes
    assert "UNILAG_SRC_1" not in futa_codes
