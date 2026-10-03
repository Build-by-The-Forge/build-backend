"""Redaction applied at the logging boundary.

Every log record passes through here (structlog processor and a stdlib
handler filter), so a secret that reaches a log call by mistake is masked
instead of written out. This is a safety net, not permission to log secrets.
"""

import logging
import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

# Field names whose values are always secret, compared case-insensitively
# with "-" treated as "_".
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "reset_token",
        "verification_token",
        "id_token",
        "code",
        "secret",
        "client_secret",
        "api_key",
        "authorization",
        "cookie",
        "set_cookie",
        "x_api_key",
        "auth_jwt_secret",
        "auth_jwt_previous_secret",
    }
)

_KEY_ALTERNATION = "|".join(sorted(SENSITIVE_KEYS, key=len, reverse=True))
_PATTERNS = (
    # JSON Web Tokens (three base64url segments, the first starting "eyJ").
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),
    # Authorization header values.
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"),
    # key=value / "key": "value" pairs for sensitive keys inside free text.
    re.compile(
        rf"""(?ix)
        (["']?\b(?:{_KEY_ALTERNATION})\b["']?\s*[:=]\s*)
        (["']?)[^\s"',&}}]+\2
        """
    ),
)


def _is_sensitive_key(key: object) -> bool:
    return isinstance(key, str) and key.lower().replace("-", "_") in SENSITIVE_KEYS


def redact_text(text: str) -> str:
    text = _PATTERNS[0].sub(REDACTED, text)
    text = _PATTERNS[1].sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    return _PATTERNS[2].sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(2)}", text)


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with secrets masked (dicts, lists, strings)."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            k: REDACTED if _is_sensitive_key(k) else redact(v) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    return value


def redact_event_dict(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor."""
    return redact(event_dict)


class RedactingFilter(logging.Filter):
    """stdlib handler filter: masks the message, its args and any traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.msg = record.getMessage()
            record.args = None
        record.msg = redact_text(str(record.msg))
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True
