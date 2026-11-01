"""Client-safe messages stay safe: no interpolated input, and no raw exception text
on a response. Static, so a new raise or route is covered the day it's written."""

import ast
import json
import re
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from app.core.exceptions import AppError, public_message
from app.domain.client_safe import ClientMessage, ClientSafeError
from app.domain.content.job import InvalidJobTransition
from app.infrastructure.content.ai_gateway import AIServiceGatewayError

ROOT = Path(__file__).resolve().parents[1] / "app"
# A status from an enum, a sequence number, a limit or another value this code
# controls. Anything else must be added here on purpose.
SAFE_VALUE = re.compile(
    r"\.value$|sequence$|^(PASSWORD_M\w+|MAX_\w+|timeout_seconds|max_bytes|what|key|minimum|stage|event_type"
    r"|self\.attempt_count|self\.max_attempts|retry_at\.isoformat\(\)|response\.status_code|type\(exc\)\.__name__"
    r"|', '\.join\(missing\)|adoption\.benchmark_version)$"
)


def _marked_class_names() -> set[str]:
    children: dict[str, set[str]] = {}
    for path in ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    children.setdefault(getattr(base, "id", getattr(base, "attr", "")), set()).add(node.name)
    names = {"ClientSafeError", "AppError"}
    pending = ["ClientMessage", "AppError", "ClientSafeError"]
    while pending:
        for child in children.get(pending.pop(), set()) - names:
            names.add(child)
            pending.append(child)
    return names


def _interpolations() -> list[str]:
    names = _marked_class_names()
    problems = []
    for path in ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
                continue
            if getattr(node.exc.func, "id", getattr(node.exc.func, "attr", "")) not in names:
                continue
            for arg in [*node.exc.args, *[k.value for k in node.exc.keywords if k.arg == "message"]]:
                for part in ast.walk(arg):
                    if isinstance(part, ast.FormattedValue):
                        source = ast.unparse(part.value)
                        if not SAFE_VALUE.search(source):
                            problems.append(f"{path.relative_to(ROOT)}:{node.lineno} {source}")
    return problems


def test_no_client_message_interpolates_anything_but_a_status_or_a_number():
    assert _interpolations() == []


def test_no_route_returns_an_exceptions_raw_text():
    raw = re.compile(r'(detail=str\(exc\)|"message": str\(exc\)|"error": str\(exc\)|"meta": \{"error": str)')
    found = [str(p.relative_to(ROOT)) for p in (ROOT / "api").rglob("*.py") if raw.search(p.read_text("utf-8"))]
    assert found == []


class _Needs(BaseModel):
    number: int


def _unmarked():
    yield ValueError("invalid literal for int() with base 10: 'the-secret-value'")
    yield RuntimeError("postgresql://user:the-secret-value@db/internal")
    yield LookupError("the-secret-value")
    try:
        _Needs(number="the-secret-value")
    except ValidationError as exc:
        yield exc
    try:
        json.loads("the-secret-value")
    except ValueError as exc:
        yield exc


class _UnmarkedAppError(Exception):
    __module__ = "app.domain.something"


@pytest.mark.parametrize("error", [*_unmarked(), _UnmarkedAppError("the-secret-value")], ids=lambda e: type(e).__name__)
def test_an_unmarked_exception_gets_the_fallback(error):
    assert public_message(error, "fallback") == "fallback"


@pytest.mark.parametrize("error", [ClientSafeError("written"), InvalidJobTransition("written"), AIServiceGatewayError("written")])
def test_a_marked_exception_keeps_its_message(error):
    assert isinstance(error, ClientMessage)
    assert public_message(error, "fallback") == "written"


def test_app_errors_keep_their_message():
    assert public_message(AppError("written"), "fallback") == "written"
