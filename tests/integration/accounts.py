"""Registering in a test. Registration answers without saying who was created, so the ID
comes from the database, not from the response."""

from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.identity.models import UserModel


async def user_id_for(email: str) -> str:
    async with SessionLocal() as session:
        user_id = await session.scalar(select(UserModel.id).where(UserModel.email == email.strip().lower()))
    assert user_id is not None, f"no account for {email}"
    return user_id


def register_and_get_id(client, payload: dict[str, Any], **request_options: Any) -> str:
    registered = client.post("/identity/users", json=payload, **request_options)
    assert registered.status_code in (201, 202), registered.text
    return client.portal.call(user_id_for, payload["email"])
