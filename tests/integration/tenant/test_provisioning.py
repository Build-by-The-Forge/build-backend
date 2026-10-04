from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.application.tenant.provisioning import (
    MembershipAction,
    ProvisioningError,
    provision_tenant,
)
from app.domain.identity.value_objects import AccountStatus, Password
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from app.infrastructure.identity.models import UserModel, UserStatus
from app.infrastructure.identity.sqlalchemy_user_repository import SQLAlchemyUserRepository
from app.infrastructure.security.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.tenant.async_repositories import (
    AsyncSqlAlchemyMembershipRepository,
    AsyncSqlAlchemyTenantRepository,
)
from sqlalchemy import func, select

PASSWORD = "Owner-Passphrase-2026"
HASHER = Argon2PasswordHasher()


def _run(session, *, slug, email, password=PASSWORD, name="Federal University of Technology, Akure"):
    return provision_tenant(
        tenants=AsyncSqlAlchemyTenantRepository(session),
        users=SQLAlchemyUserRepository(session),
        memberships=AsyncSqlAlchemyMembershipRepository(session),
        password_hasher=HASHER,
        name=name,
        slug=slug,
        owner_email=email,
        owner_password=password,
    )


def _ids():
    suffix = uuid4().hex[:10]
    return f"futa-{suffix}", f"owner-{suffix}@futa.edu.ng"


async def _count(session, model, *where):
    return await session.scalar(select(func.count()).select_from(model).where(*where))


async def _add_user(session, email, status=UserStatus.ACTIVE):
    now = datetime.now(timezone.utc)
    user_id = str(uuid4())
    session.add(
        UserModel(
            id=user_id,
            email=email,
            password_hash=HASHER.hash(Password("Existing-Pass-123")).value,
            status=status,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    return user_id


async def test_creates_tenant_owner_account_and_owner_membership(session):
    slug, email = _ids()

    result = await _run(session, slug=slug, email=email)

    assert (result.tenant_created, result.owner_created, result.membership) == (True, True, MembershipAction.CREATED)
    owner = await SQLAlchemyUserRepository(session).get_by_email(email)
    assert owner.status is AccountStatus.ACTIVE and owner.email_verified
    assert owner.password_hash.value.startswith("$argon2id$")
    membership = await session.scalar(select(MembershipModel).where(MembershipModel.tenant_id == result.tenant_id))
    assert (membership.user_id, membership.role, membership.status) == (owner.id.value, "owner", "active")
    assert result.warnings == []


async def test_a_second_run_changes_nothing(session):
    slug, email = _ids()
    first = await _run(session, slug=slug, email=email)

    again = await _run(session, slug=slug, email=email, password=None)

    assert (again.tenant_id, again.owner_user_id) == (first.tenant_id, first.owner_user_id)
    assert (again.tenant_created, again.owner_created, again.membership) == (False, False, MembershipAction.UNCHANGED)
    assert not again.owner_granted
    assert await _count(session, TenantModel, TenantModel.slug == slug) == 1
    assert await _count(session, MembershipModel, MembershipModel.tenant_id == first.tenant_id) == 1


async def test_an_existing_account_is_linked_without_touching_its_password(session):
    slug, email = _ids()
    user_id = await _add_user(session, email)
    before = (await session.get(UserModel, user_id)).password_hash

    result = await _run(session, slug=slug, email=email, password="Ignored-Passphrase-1")

    assert (result.owner_user_id, result.owner_created) == (user_id, False)
    assert (await session.get(UserModel, user_id)).password_hash == before


async def test_an_existing_member_is_promoted_and_an_archived_one_reactivated(session):
    slug, email = _ids()
    first = await _run(session, slug=slug, email=email)
    membership = await session.scalar(select(MembershipModel).where(MembershipModel.tenant_id == first.tenant_id))

    membership.role = "lecturer"
    await session.flush()
    assert (await _run(session, slug=slug, email=email)).membership is MembershipAction.PROMOTED

    membership.status = "archived"
    await session.flush()
    assert (await _run(session, slug=slug, email=email)).membership is MembershipAction.REACTIVATED
    await session.refresh(membership)
    assert (membership.role, membership.status) == ("owner", "active")


async def test_an_unverified_existing_owner_gets_a_warning(session):
    slug, email = _ids()
    await _add_user(session, email, status=UserStatus.PENDING_VERIFICATION)

    result = await _run(session, slug=slug, email=email)

    assert result.membership is MembershipAction.CREATED
    assert any("not verified" in w for w in result.warnings)


async def test_an_existing_tenant_is_not_renamed(session):
    slug, email = _ids()
    await _run(session, slug=slug, email=email)

    result = await _run(session, slug=slug, email=email, name="Some Other Name")

    tenant = await session.scalar(select(TenantModel).where(TenantModel.slug == slug))
    assert tenant.name == "Federal University of Technology, Akure"
    assert any("not renamed" in w for w in result.warnings)


@pytest.mark.parametrize("status", [UserStatus.DISABLED, UserStatus.LOCKED, UserStatus.DELETED])
async def test_blocked_accounts_cannot_become_owners(session, status):
    slug, email = _ids()
    await _add_user(session, email, status=status)

    with pytest.raises(ProvisioningError, match="cannot become an owner"):
        await _run(session, slug=slug, email=email)


async def test_an_archived_tenant_is_refused(session):
    slug, email = _ids()
    first = await _run(session, slug=slug, email=email)
    tenant = await session.get(TenantModel, first.tenant_id)
    tenant.status = "archived"
    await session.flush()

    with pytest.raises(ProvisioningError, match="archived"):
        await _run(session, slug=slug, email=email)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"password": None}, "password is required"),
        ({"password": "short"}, "at least 12"),
        ({"email": "not-an-email"}, "invalid email"),
        ({"slug": "Not A Slug!"}, "slug"),
    ],
)
async def test_invalid_input_is_refused(session, kwargs, message):
    slug, email = _ids()
    params = {"slug": slug, "email": email, **kwargs}

    with pytest.raises(ProvisioningError, match=message):
        await _run(session, **params)
