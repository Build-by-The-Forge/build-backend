import json
import logging
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.application.identity.ports.email_sender import EmailMessage

logger = logging.getLogger(__name__)


class OutboxEmailSender:
    """Development/testing sender: keeps messages in memory instead of mailing them.

    Messages carry one-time secrets, so this must never run in staging or
    production. When ``path`` is set, each message is also appended to that
    file as a JSON line so a developer can pick up codes from another shell.
    """

    def __init__(self, path: str | None = None, max_messages: int = 1000) -> None:
        self.messages: deque[EmailMessage] = deque(maxlen=max_messages)
        self._path = Path(path) if path else None

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)
        if self._path is not None:
            record = {"sent_at": datetime.now(timezone.utc).isoformat(), **asdict(message)}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

    def latest_to(self, address: str, subject: str | None = None) -> EmailMessage | None:
        for message in reversed(self.messages):
            if message.to == address and (subject is None or message.subject == subject):
                return message
        return None


class UnconfiguredEmailSender:
    """Used where no delivery provider exists yet: drops the message, loudly.

    Never logs the body, which may contain a one-time secret.
    """

    async def send(self, message: EmailMessage) -> None:
        logger.error("email delivery is not configured; dropped message %r", message.subject)
