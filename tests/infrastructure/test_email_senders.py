import json
import logging

from app.application.identity.ports.email_sender import EmailMessage
from app.bootstrap import container as container_module
from app.infrastructure.email.outbox_email_sender import (
    OutboxEmailSender,
    UnconfiguredEmailSender,
)

MESSAGE = EmailMessage(to="a@example.com", subject="Reset", body="secret-code-123")


async def test_outbox_keeps_messages_and_finds_the_latest_per_address(tmp_path):
    sender = OutboxEmailSender()
    await sender.send(MESSAGE)
    await sender.send(EmailMessage(to="a@example.com", subject="Reset", body="newer"))

    assert sender.latest_to("a@example.com").body == "newer"
    assert sender.latest_to("b@example.com") is None


async def test_outbox_appends_json_lines_when_a_path_is_set(tmp_path):
    path = tmp_path / "mail" / "outbox.jsonl"
    sender = OutboxEmailSender(str(path))

    await sender.send(MESSAGE)
    await sender.send(MESSAGE)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["body"] == "secret-code-123"


async def test_unconfigured_sender_never_logs_the_body(caplog):
    with caplog.at_level(logging.ERROR):
        await UnconfiguredEmailSender().send(MESSAGE)

    assert "not configured" in caplog.text
    assert "secret-code-123" not in caplog.text


def test_outbox_is_never_used_in_strict_environments(monkeypatch):
    for environment in ("staging", "production"):
        monkeypatch.setattr(container_module.settings, "app_environment", environment)
        assert isinstance(container_module.build_email_sender(), UnconfiguredEmailSender)

    monkeypatch.setattr(container_module.settings, "app_environment", "development")
    assert isinstance(container_module.build_email_sender(), OutboxEmailSender)
