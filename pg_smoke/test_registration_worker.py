"""The registration worker against real PostgreSQL: row locks, and racing registrations."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.api import identity
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
    assert sent == [email]


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
