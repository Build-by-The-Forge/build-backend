import io
import logging

from app.core.redaction import REDACTED, RedactingFilter, redact, redact_event_dict

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1In0.c2lnbmF0dXJl"
REFRESH = "Zq3J8r0b5mN1-t_QpWxYz7aB2cD4eF6gH8iJ0kL2mN4"


def test_sensitive_keys_are_masked_at_any_depth():
    event = {
        "event": "x",
        "password": "hunter2-hunter2",
        "Authorization": f"Bearer {JWT}",
        "payload": {"refresh_token": REFRESH, "email": "a@example.com"},
        "items": [{"new-password": "x"}],
    }

    out = redact(event)

    assert out["password"] == REDACTED
    assert out["Authorization"] == REDACTED
    assert out["payload"] == {"refresh_token": REDACTED, "email": "a@example.com"}
    assert out["items"] == [{"new-password": REDACTED}]


def test_secrets_inside_free_text_are_masked():
    text = (
        f"failed for header Bearer {JWT}; body refresh_token={REFRESH} "
        f'json {{"password": "hunter2-hunter2", "token":"{REFRESH}"}} raw {JWT}'
    )

    out = redact(text)

    for secret in (JWT, REFRESH, "hunter2-hunter2"):
        assert secret not in out
    assert "failed for header Bearer" in out


def test_ordinary_fields_are_left_alone():
    event = {"event": "request_failed", "status_code": 401, "token_type": "Bearer", "path": "/identity/refresh"}

    assert redact(event) == event


def test_structlog_processor_masks_event_dicts():
    assert redact_event_dict(None, "info", {"token": REFRESH})["token"] == REDACTED


def _capture(logger_name):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger, handler, stream


def test_stdlib_filter_masks_messages_args_and_tracebacks():
    logger, handler, stream = _capture("test.redaction.stdlib")
    try:
        logger.info("got %s", f"Authorization: Bearer {JWT}")
        try:
            raise ValueError(f"bad refresh_token={REFRESH}")
        except ValueError:
            logger.exception("boom")
    finally:
        logger.removeHandler(handler)

    output = stream.getvalue()
    assert JWT not in output and REFRESH not in output
    assert output.count(REDACTED) >= 2


def test_configure_logging_installs_the_filter_on_root_handlers():
    from app.core.logging import configure_logging

    configure_logging()

    handlers = logging.getLogger().handlers
    assert handlers
    assert all(any(isinstance(f, RedactingFilter) for f in h.filters) for h in handlers)
