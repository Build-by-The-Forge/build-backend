"""The registration worker against real PostgreSQL: row locks, and racing registrations."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.api import identity
from app.application.identity import user_service
from app.core.config import settings
from app.db.session import SessionLocal
from app.infrastructure.identity.models import PendingRegistrationModel, UserModel
from app.infrastructure.identity.sqlalchemy_pending_registration_repository import (
    SQLAlchemyPendingRegistrationRepository,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "Correct-Horse-Battery-9"


async def _counts(email: str) -> tuple[int, int]:
    async with SessionLocal() as session:
        pending_rows = await session.scalars(select(PendingRegistrationModel).where(PendingRegistrationModel.email == email))
        pending = len(pending_rows.all())
        users = len((await session.scalars(select(UserModel).where(UserModel.email == email))).all())
    return pending, users


async def test_racing_registrations_and_workers_make_one_account_and_one_email(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_inline_for_tests", False)
    email = f"race-{uuid4().hex}@example.com"
    sent: list[str] = []

    async def recording(message):
        sent.append(message.to)

    monkeypatch.setattr(identity.service.email_sender, "send", recording)
    answers = await asyncio.gather(
        *(client.post("/identity/users", json={"email": email, "password": PASSWORD}) for _ in range(4))
    )
    assert [answer.status_code for answer in answers] == [202] * 4
    assert await _counts(email) == (4, 0)

    # Workers overlap, and a row that loses the race to the unique constraint retries.
    for _ in range(4):
        await asyncio.gather(*(identity.service.process_pending_registrations() for _ in range(3)))
        if (await _counts(email))[0] == 0:
            break

    assert await _counts(email) == (0, 1)
    # Only this email: other tests may have left rows for the same worker pass.
    assert [to for to in sent if to == email] == [email]


async def test_two_workers_never_hold_the_same_row(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_inline_for_tests", False)
    email = f"lock-{uuid4().hex}@example.com"
    assert (await client.post("/identity/users", json={"email": email, "password": PASSWORD})).status_code == 202

    async with SessionLocal() as first, SessionLocal() as second:
        held = await SQLAlchemyPendingRegistrationRepository(first).claim_next(set())
        assert held is not None
        other = await SQLAlchemyPendingRegistrationRepository(second).claim_next(set())
        # Doesn't wait, and doesn't get the same row.
        assert other is None or other.id != held.id
        await first.rollback()
        await second.rollback()
    await identity.service.process_pending_registrations()


async def test_a_processed_registration_leaves_no_password_hash_behind(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_inline_for_tests", False)
    email = f"gone-{uuid4().hex}@example.com"
    await client.post("/identity/users", json={"email": email, "password": PASSWORD})
    await identity.service.process_pending_registrations()

    async with SessionLocal() as session:
        left = await session.execute(text("select count(*) from pending_registrations where email = :e"), {"e": email})
        assert left.scalar_one() == 0


async def test_counting_a_failure_on_a_row_another_worker_finished_is_harmless(client):
    # The race: this worker failed, and another finished the row before it could count that.
    async with SessionLocal() as session:
        gone = await SQLAlchemyPendingRegistrationRepository(session).record_failure(str(uuid4()), 5)
        await session.commit()
    assert gone is False


async def test_a_row_is_dropped_at_exactly_its_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_inline_for_tests", False)
    email = f"limit-{uuid4().hex}@example.com"
    await client.post("/identity/users", json={"email": email, "password": PASSWORD})
    async with SessionLocal() as session:
        row_id = await session.scalar(select(PendingRegistrationModel.id).where(PendingRegistrationModel.email == email))

    results = []
    for _ in range(3):
        async with SessionLocal() as session:
            results.append(await SQLAlchemyPendingRegistrationRepository(session).record_failure(row_id, 3))
            await session.commit()

    assert results == [False, False, True]
    assert (await _counts(email))[0] == 0


async def test_a_failure_that_cannot_be_counted_does_not_stop_the_pass(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_inline_for_tests", False)
    bad, good = f"bad-{uuid4().hex}@example.com", f"good-{uuid4().hex}@example.com"
    await client.post("/identity/users", json={"email": bad, "password": PASSWORD})
    await client.post("/identity/users", json={"email": good, "password": PASSWORD})

    real_issue = user_service.issue_email_verification

    async def failing_for_bad(repository, user, lifetime):
        if user.email.value == bad:
            raise RuntimeError("database trouble")
        return await real_issue(repository, user, lifetime)

    async def cannot_count(_registration_id, _exc):
        raise RuntimeError("database still in trouble")

    with monkeypatch.context() as broken:
        broken.setattr(user_service, "issue_email_verification", failing_for_bad)
        broken.setattr(identity.service, "_record_registration_failure", cannot_count)
        await identity.service.process_pending_registrations()

    assert await _counts(good) == (0, 1)
    assert await _counts(bad) == (1, 0)
    await identity.service.process_pending_registrations()
    assert await _counts(bad) == (0, 1)
