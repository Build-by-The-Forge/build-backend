"""Registering in a PostgreSQL test. Registration answers without saying who was created,
so the ID comes from the database, not from the response."""

from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.identity.models import UserModel


async def register_and_get_id(client, payload: dict[str, Any]) -> str:
    registered = await client.post("/identity/users", json=payload)
    assert registered.status_code == 202, registered.text
    async with SessionLocal() as session:
        user_id = await session.scalar(select(UserModel.id).where(UserModel.email == payload["email"].strip().lower()))
    assert user_id is not None, f"no account for {payload['email']}"
    return user_id
