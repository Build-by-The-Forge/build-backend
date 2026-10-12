from contextlib import asynccontextmanager

import pytest

from app.application.tenant.join_service import TenantJoinService
from app.core.exceptions import AppError
from app.domain.identity.user import User
from app.domain.identity.value_objects import AccountStatus, Email, PasswordHash, UserId
from app.domain.tenant.errors import MembershipAlreadyExistsError
from app.domain.tenant.join_policy import TenantJoinPolicy
from app.domain.tenant.membership import Membership
from app.domain.tenant.tenant import Tenant
from app.domain.tenant.value_objects import MembershipRole, MembershipStatus, TenantId, TenantName, TenantSlug
from app.domain.tenant.value_objects import UserId as MemberUserId

TENANT = Tenant.create(name=TenantName("FUTA"), slug=TenantSlug("futa"))
USER = User(id=UserId("u1"), email=Email("ada@futa.edu.ng"), password_hash=PasswordHash("h"), status=AccountStatus.ACTIVE)


class Events:
    def __init__(self):
        self.recorded = []

    async def record(self, event, **kwargs):
        self.recorded.append(event)


class World:
    """Fake repositories; ``winner`` is the membership a concurrent request created."""

    def __init__(self, winner_status=MembershipStatus.ACTIVE):
        self.winner = Membership.create(tenant_id=TENANT.id, user_id=MemberUserId("u1"), role=MembershipRole.STUDENT)
        self.winner.status = winner_status
        self.lost_race = False
        policy = TenantJoinPolicy(tenant_id=TENANT.id)
        policy.configure(enabled=True, allowed_domains=["futa.edu.ng"], updated_by_user_id=None)
        self.policy = policy

    def uow(self):
        world = self

        class Tenants:
            async def get_by_slug(self, slug):
                return TENANT

        class Memberships:
            async def get_by_tenant_user(self, tenant_id, user_id):
                return world.winner if world.lost_race else None

            async def add(self, membership):
                world.lost_race = True
                raise MembershipAlreadyExistsError("taken")

        class Users:
            async def get_by_id(self, user_id):
                return USER

        class JoinPolicies:
            async def get(self, tenant_id):
                return world.policy

        @asynccontextmanager
        async def factory():
            class Uow:
                tenants, memberships, users, join_policies = Tenants(), Memberships(), Users(), JoinPolicies()

            yield Uow()

        return factory


async def test_losing_a_concurrent_join_returns_the_winning_membership():
    world, events = World(), Events()

    result = await TenantJoinService(world.uow(), events).join("u1", "futa")

    assert (result.membership.id, result.created) == (world.winner.id, False)
    assert events.recorded == []  # only the request that created it audits it


async def test_losing_to_a_membership_that_is_not_active_is_refused():
    world = World(winner_status=MembershipStatus.ARCHIVED)

    with pytest.raises(AppError) as exc:
        await TenantJoinService(world.uow(), Events()).join("u1", "futa")

    assert exc.value.status_code == 403


async def test_a_join_creates_a_student_membership_in_the_looked_up_tenant():
    world = World()
    world.lost_race = False

    async def add(membership):
        assert membership.tenant_id == TenantId(TENANT.id.value)
        assert membership.role is MembershipRole.STUDENT

    service = TenantJoinService(world.uow(), Events())
    # Patch add on the fake to accept, then check what was created.
    result = await _join_with(service, world, add)

    assert result.created and result.membership.role is MembershipRole.STUDENT


async def _join_with(service, world, add):
    factory = world.uow()

    @asynccontextmanager
    async def accepting():
        async with factory() as uow:
            uow.memberships.add = add
            yield uow

    service._uow = accepting
    return await service.join("u1", "futa")
