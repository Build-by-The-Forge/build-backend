import pytest
from app.core.authorization import AuthorizationService, Permission
from app.core.tenant_context import TenantContext


@pytest.fixture
def context() -> TenantContext:
    return TenantContext(
        user_id="user-1",
        tenant_id="tenant-1",
        membership_id="membership-1",
        role="student",
    )


def test_student_can_read_catalogue_but_cannot_create(context: TenantContext) -> None:
    authorization = AuthorizationService()

    assert authorization.can(context, Permission.CATALOGUE_READ)
    assert not authorization.can(context, Permission.CATALOGUE_CREATE)


def test_lecturer_can_create_catalogue_content(context: TenantContext) -> None:
    authorization = AuthorizationService()
    lecturer_context = TenantContext(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        membership_id=context.membership_id,
        role="lecturer",
    )

    assert authorization.can(lecturer_context, Permission.CATALOGUE_READ)
    assert authorization.can(lecturer_context, Permission.CATALOGUE_CREATE)
    assert not authorization.can(lecturer_context, Permission.CATALOGUE_ARCHIVE)


def test_admin_can_manage_catalogue(context: TenantContext) -> None:
    authorization = AuthorizationService()
    admin_context = TenantContext(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        membership_id=context.membership_id,
        role="admin",
    )

    assert authorization.can(admin_context, Permission.CATALOGUE_READ)
    assert authorization.can(admin_context, Permission.CATALOGUE_CREATE)
    assert authorization.can(admin_context, Permission.CATALOGUE_UPDATE)
    assert authorization.can(admin_context, Permission.CATALOGUE_ARCHIVE)


def test_unknown_role_has_no_permissions(context: TenantContext) -> None:
    authorization = AuthorizationService()
    unknown_context = TenantContext(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        membership_id=context.membership_id,
        role="unknown",
    )

    assert authorization.permissions_for(unknown_context) == frozenset()
    assert not authorization.can(unknown_context, Permission.CATALOGUE_READ)


ALL_ROLES = ("student", "lecturer", "hod", "faculty_admin", "admin", "owner")


@pytest.mark.parametrize("role", ALL_ROLES)
def test_every_role_may_use_ai(context: TenantContext, role: str) -> None:
    member = TenantContext(context.user_id, context.tenant_id, context.membership_id, role)
    assert AuthorizationService().can(member, Permission.AI_USE)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_question_generation_is_for_lecturers_and_above(context: TenantContext, role: str) -> None:
    member = TenantContext(context.user_id, context.tenant_id, context.membership_id, role)
    expected = role != "student"
    assert AuthorizationService().can(member, Permission.AI_QUESTIONS_GENERATE) is expected
