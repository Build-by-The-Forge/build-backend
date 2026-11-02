"""Registering in a PostgreSQL test. Registration answers without saying who was created,
so the ID comes from the database, not from the response."""

import asyncio
import time
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.identity.models import UserModel


async def register_and_get_id(client, payload: dict[str, Any]) -> str:
    registered = await client.post("/identity/users", json=payload)
    assert registered.status_code == 202, registered.text
    # Registrations racing each other can briefly hold this row (SKIP LOCKED), so the
    # account may be a moment behind the answer, as it can in production.
    deadline = time.monotonic() + 10
    while True:
        async with SessionLocal() as session:
            user_id = await session.scalar(select(UserModel.id).where(UserModel.email == payload["email"].strip().lower()))
        if user_id is not None:
            return user_id
        assert time.monotonic() < deadline, f"no account for {payload['email']}"
        await asyncio.sleep(0.05)
