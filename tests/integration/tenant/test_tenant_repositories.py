from datetime import datetime, timezone
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domain.tenant.membership import Membership
from app.domain.tenant.tenant import Tenant
from app.domain.tenant.value_objects import (
    MembershipRole,
    MembershipStatus,
    MembershipId,
    TenantId,
    TenantName,
    TenantSlug,
    UserId,
)
from app.infrastructure.tenant.repositories import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyTenantRepository,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_tenant(name: str, slug: str, tenant_id: str) -> Tenant:
    now = datetime.now(timezone.utc)
    return Tenant(
        id=TenantId(tenant_id),
        name=TenantName(name),
        slug=TenantSlug(slug),
        created_at=now,
        updated_at=now,
    )


def test_tenant_repository_round_trips_and_finds_by_slug(db_session: Session) -> None:
    tenant = make_tenant("FUTA", "futa", "tenant-futa")
    repository = SqlAlchemyTenantRepository(db_session)

    repository.add(tenant)
    db_session.commit()

    by_id = repository.get_by_id("tenant-futa")
    by_slug = repository.get_by_slug("futa")

    assert by_id is not None
    assert by_id.name.value == "FUTA"
    assert by_slug is not None
    assert by_slug.id.value == "tenant-futa"
    assert repository.get_by_slug("missing") is None


def test_tenant_repository_lists_all_tenants_without_cross_tenant_filtering(
    db_session: Session,
) -> None:
    repository = SqlAlchemyTenantRepository(db_session)
    repository.add(make_tenant("FUTA", "futa", "tenant-futa"))
    repository.add(make_tenant("Other University", "other-university", "tenant-other"))
    db_session.commit()

    tenants = repository.list_all()

    assert {tenant.id.value for tenant in tenants} == {"tenant-futa", "tenant-other"}


def make_membership(
    tenant_id: str,
    user_id: str,
    membership_id: str,
    role: MembershipRole = MembershipRole.STUDENT,
) -> Membership:
    now = datetime.now(timezone.utc)
    return Membership(
        id=MembershipId(membership_id),
        tenant_id=TenantId(tenant_id),
        user_id=UserId(user_id),
        role=role,
        status=MembershipStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def test_membership_repository_resolves_by_tenant_and_user(db_session: Session) -> None:
    repository = SqlAlchemyMembershipRepository(db_session)
    repository.add(make_membership("tenant-futa", "user-1", "membership-1"))
    repository.add(make_membership("tenant-other", "user-1", "membership-2"))
    repository.add(make_membership("tenant-futa", "user-2", "membership-3"))
    db_session.commit()

    membership = repository.get_by_tenant_user("tenant-futa", "user-1")

    assert membership is not None
    assert membership.id.value == "membership-1"
    assert membership.role is MembershipRole.STUDENT
    assert repository.get_by_tenant_user("tenant-other", "user-2") is None


def test_membership_repository_returns_none_for_unknown_membership(
    db_session: Session,
) -> None:
    repository = SqlAlchemyMembershipRepository(db_session)

    assert repository.get_by_tenant_user("tenant-futa", "missing-user") is None
