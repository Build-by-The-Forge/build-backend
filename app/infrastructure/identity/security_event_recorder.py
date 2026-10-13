import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.identity.ports.security_events import (
    LoginFailureReason,
    SecurityEvent,
)
from app.core.redaction import redact
from app.core.request_context import current_request
from app.infrastructure.identity.models import LoginEventModel, SecurityEventModel

logger = structlog.get_logger(__name__)

MAX_USER_AGENT_LENGTH = 512


class SQLAlchemySecurityEventRecorder:
    """Writes each event in its own short transaction.

    Separate from the request's unit of work on purpose: failed sign-ins and
    detected attacks must be recorded even though the request's own
    transaction rolls back. Request id, client IP and user agent come from
    the current request context.
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(
        self,
        event: SecurityEvent,
        *,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        meta = current_request.get()
        payload = {"request_id": meta.request_id, **redact(metadata or {})}
        event_type, action = event.value
        await self._write(
            SecurityEventModel(
                id=str(uuid4()),
                user_id=user_id,
                event_type=event_type,
                action=action,
                meta_data=json.dumps(payload, default=str),
                ip_address=meta.ip,
            ),
            event=f"{event_type}.{action}",
        )

    async def record_login(
        self,
        *,
        user_id: str | None,
        successful: bool,
        reason: LoginFailureReason | None = None,
    ) -> None:
        meta = current_request.get()
        await self._write(
            LoginEventModel(
                id=str(uuid4()),
                user_id=user_id,
                ip_address=meta.ip,
                user_agent=(meta.user_agent or None) and meta.user_agent[:MAX_USER_AGENT_LENGTH],
                successful=successful,
                reason=reason.value if reason else None,
            ),
            event="login",
        )

    async def _write(self, model: Any, *, event: str) -> None:
        try:
            async with self._session_factory() as session:
                session.add(model)
                await session.commit()
        except Exception as exc:
            # Recording must never break authentication.
            logger.error(
                "security_event_record_failed",
                security_event=event,
                exception_type=type(exc).__name__,
            )
