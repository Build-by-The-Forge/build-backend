"""S-02 on real PostgreSQL, at the profile store: concurrent saves, the
membership lock held for the whole save, refusals at the data-access
boundary, and generic plans."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update

from app.application.academic.profile_service import AcademicProfileService
from app.bootstrap.container import sqlalchemy_academic_profiles
from app.db.session import SessionLocal
from app.domain.academic.profile import NotAStudentMember, UnavailableReferences
from app.infrastructure.academic.profile_repository import SqlAlchemyAcademicProfileRepository
from app.infrastructure.db.models.academic import AcademicProfileModel
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import MembershipModel
from app.infrastructure.identity.models import UserModel
from pg_smoke.test_migration_0032 import _world

pytestmark = pytest.mark.asyncio(loop_scope="session")

service = AcademicProfileService(sqlalchemy_academic_profiles)


async def _courses(w: dict[str, str], count: int) -> list[str]:
    now = datetime.now(timezone.utc)
    ids = [str(uuid4()) for _ in range(count)]
    async with SessionLocal() as session:
        for i, course_id in enumerate(ids):
            session.add(
                CourseModel(
                    id=course_id,
                    tenant_id=w["tenant"],
                    department_id=w["department"],
                    code=f"X{uuid4().hex[:6]}{i}",
                    title="T",
                    slug=f"x-{uuid4().hex[:10]}",
                    credit_units=2,
                    level=300,
                    semester=1,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()
    return ids


async def _another_student(w: dict[str, str]) -> str:
    """A further student member of the world's tenant."""
    now = datetime.now(timezone.utc)
    user_id = str(uuid4())
    async with SessionLocal() as session:
        session.add(UserModel(id=user_id, email=f"s02-{uuid4().hex}@example.com", password_hash="x"))
        await session.flush()
        session.add(
            MembershipModel(
                id=str(uuid4()),
                tenant_id=w["tenant"],
                user_id=user_id,
                role="student",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    return user_id


async def _profiles(session, user_id: str) -> int:
    return await session.scalar(
        select(func.count()).select_from(AcademicProfileModel).where(AcademicProfileModel.user_id == user_id)
    )


async def _stored(w: dict[str, str], user_id: str) -> set[str]:
    return {c.id for c in (await service.get(w["tenant"], user_id)).courses}


async def test_a_save_waiting_on_another_replaces_what_that_one_committed():
    """The forced order: one save holds the profile row; the second waits on
    it, then deletes the first's committed courses and stores only its own."""
    w = await _world()
    first, second = await _courses(w, 2), await _courses(w, 1)
    await service.replace(w["tenant"], w["user"], w["programme"], 300, [])

    async with SessionLocal() as session:
        holder = SqlAlchemyAcademicProfileRepository(session)
        async with session.begin():
            await holder.replace(w["tenant"], w["user"], w["programme"], 300, first)
            waiting = asyncio.create_task(service.replace(w["tenant"], w["user"], w["programme"], 300, second))
            await asyncio.sleep(0.5)
            assert not waiting.done(), "the second save didn't wait for the profile row's lock"
        await waiting

    assert await _stored(w, w["user"]) == set(second)


@pytest.mark.parametrize("first_save", [True, False], ids=["first saves", "later saves"])
async def test_concurrent_saves_store_exactly_one_of_them_forty_times_out_of_forty(first_save):
    w = await _world()
    a, b = await _courses(w, 3), await _courses(w, 2)
    for _ in range(40):
        user_id = await _another_student(w) if first_save else w["user"]
        await asyncio.gather(
            service.replace(w["tenant"], user_id, w["programme"], 300, a),
            service.replace(w["tenant"], user_id, w["programme"], 300, b),
        )
        assert await _stored(w, user_id) in (set(a), set(b))
        async with SessionLocal() as session:
            rows = await session.scalar(
                select(func.count())
                .select_from(AcademicProfileModel)
                .where(AcademicProfileModel.tenant_id == w["tenant"], AcademicProfileModel.user_id == user_id)
            )
        assert rows == 1


async def test_the_reads_and_the_save_stay_right_past_five_runs():
    """PostgreSQL may switch a statement to a generic plan after five runs."""
    w = await _world()
    sets = [await _courses(w, n) for n in (1, 3, 2)]
    for run in range(9):
        chosen = sets[run % 3]
        saved = await service.replace(w["tenant"], w["user"], w["programme"], 300, chosen)
        assert {c.id for c in saved.courses} == set(chosen)
        assert await _stored(w, w["user"]) == set(chosen)
        with pytest.raises(UnavailableReferences):
            await service.replace(w["tenant"], w["user"], str(uuid4()), 300, chosen)


@pytest.mark.parametrize(
    ("role", "status"),
    [("lecturer", "active"), ("admin", "active"), ("owner", "active"), ("student", "archived"), ("student", "invited")],
)
async def test_the_profile_store_itself_refuses_anyone_but_an_active_student(role, status):
    """Enforced where the profile is read and written, not only by the route."""
    w = await _world()
    async with SessionLocal() as session:
        await session.execute(update(MembershipModel).where(MembershipModel.id == w["member"]).values(role=role, status=status))
        await session.commit()

    with pytest.raises(NotAStudentMember):
        await service.get(w["tenant"], w["user"])
    with pytest.raises(NotAStudentMember):
        await service.replace(w["tenant"], w["user"], w["programme"], 300, [w["course"]])
    async with SessionLocal() as session:
        assert await _profiles(session, w["user"]) == 0


async def test_a_user_without_a_membership_in_the_tenant_has_no_profile_there():
    w, other = await _world(), await _world()

    with pytest.raises(NotAStudentMember):
        await service.replace(other["tenant"], w["user"], other["programme"], 300, [])


# --- The authorization holds for the whole save --------------------------------------
# A save takes the membership FOR SHARE, then the profile row, in one transaction.
# Removing or changing a membership locks the membership first, then (by cascade)
# the profile: the same order, so the two serialize instead of deadlocking.


async def _change_membership(w: dict[str, str], change: str) -> None:
    async with SessionLocal() as session:
        if change == "deleted":
            await session.execute(delete(MembershipModel).where(MembershipModel.id == w["member"]))
        else:
            values = {"status": "archived"} if change == "archived" else {"role": "lecturer"}
            await session.execute(update(MembershipModel).where(MembershipModel.id == w["member"]).values(**values))
        await session.commit()


@pytest.mark.parametrize(("change", "profiles_after"), [("archived", 1), ("made staff", 1), ("deleted", 0)])
async def test_a_membership_change_waits_for_the_save_it_would_invalidate(change, profiles_after):
    """The save's membership lock is held until the profile write commits."""
    w = await _world()
    async with SessionLocal() as session:
        holder = SqlAlchemyAcademicProfileRepository(session)
        async with session.begin():
            await holder.replace(w["tenant"], w["user"], w["programme"], 300, [w["course"]])
            changing = asyncio.create_task(_change_membership(w, change))
            await asyncio.sleep(0.5)
            assert not changing.done(), "the membership changed under an uncommitted save"
        await changing

    # The save committed first, then the change applied to it.
    async with SessionLocal() as session:
        assert await _profiles(session, w["user"]) == profiles_after
    with pytest.raises(NotAStudentMember):
        await service.get(w["tenant"], w["user"])


@pytest.mark.parametrize("change", ["archived", "made staff", "deleted"])
async def test_a_save_waits_for_a_membership_change_in_progress_then_refuses(change):
    w = await _world()
    async with SessionLocal() as session:
        async with session.begin():
            if change == "deleted":
                await session.execute(delete(MembershipModel).where(MembershipModel.id == w["member"]))
            else:
                values = {"status": "archived"} if change == "archived" else {"role": "lecturer"}
                await session.execute(update(MembershipModel).where(MembershipModel.id == w["member"]).values(**values))
            saving = asyncio.create_task(service.replace(w["tenant"], w["user"], w["programme"], 300, [w["course"]]))
            await asyncio.sleep(0.5)
            assert not saving.done(), "the save didn't wait for the membership change"
        with pytest.raises(NotAStudentMember):
            await saving

    async with SessionLocal() as session:
        assert await _profiles(session, w["user"]) == 0
