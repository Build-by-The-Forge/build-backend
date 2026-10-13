from uuid import UUID

import pytest
from app.domain.content.enums import (
    AuthorityLevel,
    ContentSourceType,
    SourceStatus,
    VisibilityScope,
)
from app.domain.content.source import ContentSource


def test_create_regulatory_content_source_success() -> None:
    source = ContentSource.create(
        code="NUC_CCMAS_CS",
        name="National Universities Commission CCMAS Computer Science",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-admin",
        created_by_email="admin@nuc.gov.ng",
        source_url="https://ccmas.nuc.edu.ng/cs",
        description="Official national regulatory benchmark curriculum for computer science.",
    )

    assert str(UUID(source.id)) == source.id and UUID(source.id).version == 4  # fits VARCHAR(36)
    assert source.code == "NUC_CCMAS_CS"
    assert source.name == "National Universities Commission CCMAS Computer Science"
    assert source.source_type == ContentSourceType.CCMAS
    assert source.authority_level == AuthorityLevel.REGULATORY
    assert source.authority_level.rank == 1
    assert source.visibility == VisibilityScope.PLATFORM
    assert source.status == SourceStatus.ACTIVE
    assert source.tenant_id is None

    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.source_created"
    assert events[0].payload["code"] == "NUC_CCMAS_CS"
    assert events[0].payload["authority_level"] == "regulatory"


def test_create_institutional_content_source_success() -> None:
    source = ContentSource.create(
        code="FUTA_CSC_NOTES",
        name="FUTA Computer Science Lecture Notes",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.DEPARTMENT,
        created_by="usr-lecturer",
        created_by_email="adewale@futa.edu.ng",
        tenant_id="tenant-futa",
        faculty_id="fac-seet",
        department_id="dept-csc",
        author_name="Dr. Adewale",
    )

    assert str(UUID(source.id)) == source.id and UUID(source.id).version == 4  # fits VARCHAR(36)
    assert source.code == "FUTA_CSC_NOTES"
    assert source.authority_level == AuthorityLevel.INSTITUTIONAL
    assert source.authority_level.rank == 2
    assert source.visibility == VisibilityScope.DEPARTMENT
    assert source.tenant_id == "tenant-futa"
    assert source.department_id == "dept-csc"

    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.source_created"
    assert events[0].payload["tenant_id"] == "tenant-futa"


def test_regulatory_invariants_enforced() -> None:
    # Regulatory with tenant_id -> REJECT
    with pytest.raises(
        ValueError,
        match="regulatory content sources cannot be scoped to a single tenant",
    ):
        ContentSource.create(
            code="REG_FAIL",
            name="Regulatory Fail",
            source_type=ContentSourceType.CCMAS,
            authority_level=AuthorityLevel.REGULATORY,
            visibility=VisibilityScope.PLATFORM,
            created_by="admin",
            created_by_email="admin@test.com",
            tenant_id="tenant-123",
        )

    # Regulatory with non-platform visibility -> REJECT
    with pytest.raises(
        ValueError, match="regulatory content sources must have platform visibility"
    ):
        ContentSource.create(
            code="REG_FAIL_2",
            name="Regulatory Fail 2",
            source_type=ContentSourceType.CCMAS,
            authority_level=AuthorityLevel.REGULATORY,
            visibility=VisibilityScope.TENANT,
            created_by="admin",
            created_by_email="admin@test.com",
            tenant_id="tenant-123",
        )


def test_institutional_invariants_enforced() -> None:
    # Institutional with platform visibility -> REJECT
    with pytest.raises(
        ValueError,
        match="institutional content sources cannot have platform-wide visibility",
    ):
        ContentSource.create(
            code="INST_FAIL",
            name="Institutional Fail",
            source_type=ContentSourceType.LECTURER_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.PLATFORM,
            created_by="lecturer",
            created_by_email="lecturer@test.com",
        )


def test_visibility_scope_invariants_enforced() -> None:
    # Tenant scope without tenant_id -> REJECT
    with pytest.raises(ValueError, match="requires a valid tenant_id"):
        ContentSource.create(
            code="SCOP_FAIL_1",
            name="Scope Fail 1",
            source_type=ContentSourceType.TEXTBOOK,
            authority_level=AuthorityLevel.APPROVED_REFERENCE,
            visibility=VisibilityScope.TENANT,
            created_by="admin",
            created_by_email="admin@test.com",
            tenant_id=None,
        )

    # Faculty scope without faculty_id -> REJECT
    with pytest.raises(
        ValueError, match="faculty visibility scope requires faculty_id"
    ):
        ContentSource.create(
            code="SCOP_FAIL_2",
            name="Scope Fail 2",
            source_type=ContentSourceType.ADMIN_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.FACULTY,
            created_by="admin",
            created_by_email="admin@test.com",
            tenant_id="tenant-1",
            faculty_id=None,
        )

    # Department scope without department_id -> REJECT
    with pytest.raises(
        ValueError, match="department visibility scope requires department_id"
    ):
        ContentSource.create(
            code="SCOP_FAIL_3",
            name="Scope Fail 3",
            source_type=ContentSourceType.LECTURER_UPLOAD,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.DEPARTMENT,
            created_by="admin",
            created_by_email="admin@test.com",
            tenant_id="tenant-1",
            department_id=None,
        )

    # Programme scope without programme_id -> REJECT
    with pytest.raises(
        ValueError, match="programme visibility scope requires programme_id"
    ):
        ContentSource.create(
            code="SCOP_FAIL_4",
            name="Scope Fail 4",
            source_type=ContentSourceType.COURSE_MATERIAL,
            authority_level=AuthorityLevel.INSTITUTIONAL,
            visibility=VisibilityScope.PROGRAMME,
            created_by="admin",
            created_by_email="admin@test.com",
            tenant_id="tenant-1",
            programme_id=None,
        )


def test_status_transitions_and_metadata_updates() -> None:
    source = ContentSource.create(
        code="TEXTBOOK_DS",
        name="Data Structures in Python",
        source_type=ContentSourceType.TEXTBOOK,
        authority_level=AuthorityLevel.APPROVED_REFERENCE,
        visibility=VisibilityScope.TENANT,
        created_by="admin",
        created_by_email="admin@test.com",
        tenant_id="tenant-futa",
    )
    source.pull_events()

    # Update metadata
    source.update_metadata(
        name="Data Structures and Algorithms in Python (2nd Ed)",
        author_name="Michael T. Goodrich",
        publisher="Wiley",
        isbn_or_doi="978-1118290279",
    )
    assert source.name == "Data Structures and Algorithms in Python (2nd Ed)"
    assert source.author_name == "Michael T. Goodrich"
    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.source_updated"

    # Deprecate
    source.deprecate(reason="Superceded by 3rd Edition")
    assert source.status == SourceStatus.DEPRECATED
    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.source_deprecated"
    assert events[0].payload["reason"] == "Superceded by 3rd Edition"

    # Reactivate
    source.activate()
    assert source.status == SourceStatus.ACTIVE
    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.source_activated"

    # Revoke
    source.revoke(reason="Copyright infringement claim")
    assert source.status == SourceStatus.REVOKED
    events = source.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.source_revoked"

    # Cannot update metadata when revoked
    with pytest.raises(
        ValueError, match="cannot update metadata of a revoked content source"
    ):
        source.update_metadata(name="New Name")

    # Cannot deprecate when revoked
    with pytest.raises(ValueError, match="cannot deprecate a revoked content source"):
        source.deprecate(reason="test")


def test_is_accessible_by_scoping_rules() -> None:
    # 1. Platform source
    plat_source = ContentSource.create(
        code="CCMAS",
        name="CCMAS",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="admin",
        created_by_email="admin@nuc.ng",
    )
    assert plat_source.is_accessible_by(tenant_id="tenant-futa") is True
    assert plat_source.is_accessible_by(tenant_id="tenant-unilag") is True
    assert plat_source.is_accessible_by(tenant_id=None) is True

    # 2. Tenant source
    tenant_source = ContentSource.create(
        code="FUTA_REF",
        name="FUTA Reference",
        source_type=ContentSourceType.TEXTBOOK,
        authority_level=AuthorityLevel.APPROVED_REFERENCE,
        visibility=VisibilityScope.TENANT,
        created_by="admin",
        created_by_email="admin@futa.edu.ng",
        tenant_id="tenant-futa",
    )
    assert tenant_source.is_accessible_by(tenant_id="tenant-futa") is True
    assert tenant_source.is_accessible_by(tenant_id="tenant-unilag") is False
    assert tenant_source.is_accessible_by(tenant_id=None) is False

    # 3. Department source
    dept_source = ContentSource.create(
        code="FUTA_CSC_HANDOUT",
        name="CSC Handout",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.DEPARTMENT,
        created_by="lecturer",
        created_by_email="lecturer@futa.edu.ng",
        tenant_id="tenant-futa",
        faculty_id="fac-science",
        department_id="dept-csc",
    )
    assert (
        dept_source.is_accessible_by(tenant_id="tenant-futa", department_id="dept-csc")
        is True
    )
    assert (
        dept_source.is_accessible_by(tenant_id="tenant-futa", department_id="dept-mth")
        is False
    )
    assert (
        dept_source.is_accessible_by(
            tenant_id="tenant-unilag", department_id="dept-csc"
        )
        is False
    )

    # 4. Revoked source is never accessible
    tenant_source.revoke(reason="Removed")
    assert tenant_source.is_accessible_by(tenant_id="tenant-futa") is False
