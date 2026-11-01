"""The disclosure boundary. At runtime, the handlers are the final point: unmarked text
never leaves, whoever raised it. Statically, marked text is held to what's written
here, so a new raise or route is covered the day it's written."""

import ast
import enum
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Literal, get_args
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_core.core_schema import ErrorType

from app.core.exceptions import (
    _VALIDATION_MESSAGES,
    AppError,
    ClientError,
    ClientHTTPException,
    NotFoundError,
    RateLimitedError,
    _safe_validation_message,
    public_message,
    safe_validation_details,
)
from app.domain.client_safe import ClientMessage, ClientSafeError
from app.domain.content.ai_report import safe_evidence
from app.domain.content.job import InvalidJobTransition
from app.infrastructure.content.ai_gateway import AIServiceGatewayError
from app.main import add_response_middleware, app

ROOT = Path(__file__).resolve().parents[1] / "app"
LEAK = "http://ai-service.internal:8000/v1 password=hunter2 sk-provider-key"

# Values this code controls: a status from an enum, a sequence number, a limit from
# configuration. Anything else must be added here on purpose.
SAFE_VALUE = re.compile(
    r"\.value$|sequence$|^(PASSWORD_M\w+|MAX_\w+|timeout_seconds|max_bytes|what|key|minimum"
    r"|self\.attempt_count|self\.max_attempts|retry_at\.isoformat\(\)|response\.status_code|type\(exc\)\.__name__"
    r"|', '\.join\(missing\)|adoption\.benchmark_version)$"
)
# Listed above as parameters, so safe only if every caller passes a literal. Checked below.
CONTROLLED_PARAMETERS = {"what", "key", "minimum"}
SAFE_CALLS = {"public_message", "public_failure_message"}


def _modules():
    for path in ROOT.rglob("*.py"):
        yield path, ast.parse(path.read_text("utf-8"))


def _marked_class_names() -> set[str]:
    children: dict[str, set[str]] = {}
    for _, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    children.setdefault(getattr(base, "id", getattr(base, "attr", "")), set()).add(node.name)
    names = {"ClientSafeError"}
    pending = ["ClientMessage"]
    while pending:
        for child in children.get(pending.pop(), set()) - names:
            names.add(child)
            pending.append(child)
    return names


def _string_constants(tree: ast.Module) -> set[str]:
    """Names this module assigns once, at its top level, to a literal string."""
    assigned: dict[str, list[ast.expr]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
    top_level = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    return {
        name
        for name, values in assigned.items()
        if name in top_level and len(values) == 1 and isinstance(values[0], ast.Constant) and isinstance(values[0].value, str)
    }


def _unsafe_parts(text: ast.expr, constants: set[str] = frozenset()) -> list[str]:
    if isinstance(text, ast.Constant):
        return []
    if isinstance(text, ast.Name) and text.id in constants:
        return []
    if isinstance(text, ast.Call) and getattr(text.func, "id", "") in SAFE_CALLS:
        return []
    if isinstance(text, ast.JoinedStr):
        parts = [p.value for p in text.values if isinstance(p, ast.FormattedValue)]
        return [ast.unparse(p) for p in parts if not SAFE_VALUE.search(ast.unparse(p))]
    return [ast.unparse(text)]


def _marked_text_problems() -> list[str]:
    """Every construction, not only `raise`: errors are also built and returned, or kept
    in a variable. Exceptions whose first argument isn't message text are listed here."""
    names = _marked_class_names()
    not_text = {"RateLimitedError", "DuplicateContentError"}
    problems = []
    for path, tree in _modules():
        constants = _string_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if called not in names or called in not_text:
                continue
            texts = list(node.args[:1]) + [k.value for k in node.keywords if k.arg in ("message", "detail")]
            for text in texts:
                problems += [f"{path.relative_to(ROOT)}:{node.lineno} {part}" for part in _unsafe_parts(text, constants)]
    return problems


def test_every_marked_error_holds_only_written_text():
    problems = _marked_text_problems()
    assert not problems, " | ".join(problems)


def _functions_taking_controlled_parameters():
    for _, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                names = [a.arg for a in node.args.args]
                raises = [part for part in ast.walk(node) if isinstance(part, ast.Raise)]
                for parameter in CONTROLLED_PARAMETERS & set(names):
                    if any(_interpolates(part, parameter) for raised in raises for part in ast.walk(raised)):
                        yield node.name, parameter, names.index(parameter)


def _interpolates(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name) and node.value.id == name


def test_a_listed_parameter_only_ever_receives_a_literal():
    # A name proves nothing: what matters is where the value comes from.
    functions = list(_functions_taking_controlled_parameters())
    assert functions, "the check must find what it guards"
    problems = []
    for path, tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", getattr(node.func, "attr", ""))
            for function, parameter, position in functions:
                if called != function:
                    continue
                passed = [k.value for k in node.keywords if k.arg == parameter]
                passed += node.args[position : position + 1]
                problems += [
                    f"{path.relative_to(ROOT)}:{node.lineno} {parameter}={ast.unparse(value)}"
                    for value in passed
                    if not isinstance(value, ast.Constant)
                ]
    assert not problems, " | ".join(problems)


def test_no_error_body_on_a_route_carries_unchecked_text():
    problems = []
    for path, tree in _modules():
        if not str(path.relative_to(ROOT)).startswith(("api", "middleware")):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "message":
                    problems += [f"{path.relative_to(ROOT)}:{node.lineno} {p}" for p in _unsafe_parts(value)]
    assert problems == []


def test_the_handlers_are_the_only_place_detail_or_message_becomes_text():
    source = (ROOT / "core" / "exceptions.py").read_text("utf-8")
    assert "isinstance(exc, ClientMessage) else message_for_status" in source
    assert source.count("str(exc.detail)") == 1


# --- at runtime, through the application's real handlers ------------------------------


def _app_raising(error: Exception) -> FastAPI:
    subject = FastAPI()
    add_response_middleware(subject, [])
    for kind, handler in app.exception_handlers.items():
        if kind is not Exception:
            subject.add_exception_handler(kind, handler)

    @subject.get("/raise")
    async def raises():
        raise error

    return subject


def _answer(error: Exception):
    with TestClient(_app_raising(error)) as client:
        return client.get("/raise")


@pytest.mark.parametrize(
    "error,status_code,message",
    [
        (AppError(LEAK, status_code=409), 409, "the request conflicts with the current state"),
        (AppError(LEAK, status_code=502, code="AI_UPSTREAM_ERROR"), 502, "something went wrong"),
        (AppError(LEAK), 500, "something went wrong"),
        (HTTPException(status_code=400, detail=LEAK), 400, "the request could not be completed"),
        (HTTPException(status_code=404, detail=LEAK), 404, "resource not found"),
        (HTTPException(status_code=403, detail=LEAK), 403, "permission denied"),
        (HTTPException(status_code=503, detail=LEAK), 503, "something went wrong"),
    ],
    ids=lambda v: type(v).__name__ if isinstance(v, Exception) else None,
)
def test_an_unmarked_error_never_reaches_the_client(error, status_code, message):
    response = _answer(error)
    assert response.status_code == status_code
    assert response.json()["error"]["message"] == message
    assert "hunter2" not in response.text
    assert "ai-service.internal" not in response.text


def test_an_unmarked_error_keeps_its_code():
    assert _answer(AppError(LEAK, status_code=409, code="ATTEMPT_EXPIRED")).json()["error"]["code"] == "ATTEMPT_EXPIRED"


@pytest.mark.parametrize(
    "error,status_code",
    [
        (ClientError("written for you", status_code=409), 409),
        (ClientHTTPException(status_code=404, detail="written for you"), 404),
    ],
    ids=lambda v: type(v).__name__ if isinstance(v, Exception) else None,
)
def test_a_marked_error_keeps_its_approved_message(error, status_code):
    response = _answer(error)
    assert response.status_code == status_code
    assert response.json()["error"]["message"] == "written for you"


def test_marked_subclasses_keep_their_messages():
    assert _answer(RateLimitedError(5)).json()["error"]["message"] == "too many requests"
    assert _answer(NotFoundError()).json()["error"]["message"] == "Resource not found"


def test_an_http_exception_keeps_its_headers():
    response = _answer(HTTPException(status_code=401, detail=LEAK, headers={"WWW-Authenticate": "Bearer"}))
    assert response.headers["www-authenticate"] == "Bearer"
    assert "hunter2" not in response.text


def test_the_frameworks_own_errors_get_fixed_text():
    with TestClient(app) as client:
        assert client.get("/no-such-route").json()["error"]["message"] == "resource not found"
        assert client.delete("/identity/authenticate").json()["error"]["message"] == "method not allowed"


# --- validation -------------------------------------------------------------------------


class _Colour(enum.Enum):
    RED = "red"


class _Validated(BaseModel):
    @model_validator(mode="after")
    def refuse(self):
        raise ValueError(LEAK)


class _ValidatedSafely(BaseModel):
    @model_validator(mode="after")
    def refuse(self):
        raise ClientSafeError("written for you")


def _posting(model) -> TestClient:
    subject = FastAPI()
    for kind, handler in app.exception_handlers.items():
        if kind is not Exception:
            subject.add_exception_handler(kind, handler)

    @subject.post("/validate")
    async def validate(body: model):  # type: ignore[valid-type]
        return {}

    return TestClient(subject)


def test_a_validators_unmarked_text_never_reaches_the_client():
    response = _posting(_Validated).post("/validate", json={})
    assert response.status_code == 422
    assert "hunter2" not in response.text
    assert response.json()["error"]["details"]["fields"][0]["message"] == "invalid value"


def test_a_validators_marked_text_is_kept():
    response = _posting(_ValidatedSafely).post("/validate", json={})
    assert "written for you" in response.json()["error"]["details"]["fields"][0]["message"]


def test_only_a_declared_name_appears_as_a_field():
    errors = [{"type": "missing", "loc": ("body", "email", 2, "looks-like-a-field", "password=hunter2"), "msg": ""}]
    assert safe_validation_details(errors, {"email"})["fields"][0]["field"] == "body.email.2.*.*"


def test_a_declared_field_is_still_named_through_the_app():
    response = _posting(_EveryConstraint).post("/validate", json={"required": 7})
    assert response.json()["error"]["details"]["fields"][0]["field"] == "body.required"


def test_a_submitted_key_is_not_echoed_as_a_field_name():
    class Strict(BaseModel):
        model_config = {"extra": "forbid"}

    response = _posting(Strict).post("/validate", json={"password=hunter2": 1})
    assert response.status_code == 422
    assert "hunter2" not in response.text


def test_every_pydantic_error_type_gets_written_text():
    for kind in get_args(ErrorType):
        message = _safe_validation_message({"type": kind, "msg": LEAK, "ctx": {"error": ValueError(LEAK)}})
        assert message in {*_VALIDATION_MESSAGES.values(), "invalid value"}, kind


def test_the_table_names_only_real_error_types():
    assert set(_VALIDATION_MESSAGES) <= set(get_args(ErrorType))


def test_a_code_that_is_not_a_plain_identifier_is_replaced():
    details = safe_validation_details([{"type": LEAK, "loc": ("body",), "msg": LEAK}], ())
    assert details == {"fields": [{"field": "body", "code": "invalid", "message": "invalid value"}]}


class _EveryConstraint(BaseModel):
    model_config = {"extra": "forbid"}

    required: str = Field(min_length=3, max_length=5, pattern="^[a-z]+$")
    number: int = Field(default=1, ge=1, le=5)
    ratio: float = Field(default=1.0, gt=0, lt=5)
    flag: bool = True
    choice: Literal["a", "b"] = "a"
    colour: _Colour = _Colour.RED
    when: datetime | None = None
    identity: UUID | None = None
    items: list[str] = Field(default_factory=list, max_length=1)
    nested: dict[str, int] = Field(default_factory=dict)


SECRET = "the-secret-value"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"required": SECRET},
        {"required": "ab"},
        {"required": 7},
        {"required": "abc", "number": SECRET},
        {"required": "abc", "number": 99},
        {"required": "abc", "ratio": SECRET},
        {"required": "abc", "ratio": 99},
        {"required": "abc", "flag": SECRET},
        {"required": "abc", "choice": SECRET},
        {"required": "abc", "colour": SECRET},
        {"required": "abc", "when": SECRET},
        {"required": "abc", "identity": SECRET},
        {"required": "abc", "items": [SECRET, SECRET]},
        {"required": "abc", "items": SECRET},
        {"required": "abc", "nested": SECRET},
        {"required": "abc", "nested": {SECRET: SECRET}},
        {"required": "abc", SECRET: 1},
        [SECRET],
    ],
    ids=lambda body: "-".join(body) if isinstance(body, dict) else "not-an-object",
)
def test_no_refusal_of_any_constraint_echoes_the_value(body):
    response = _posting(_EveryConstraint).post("/validate", json=body)
    assert response.status_code == 422, response.text
    assert SECRET not in response.text
    for field in response.json()["error"]["details"]["fields"]:
        assert field["message"] in {*_VALIDATION_MESSAGES.values(), "invalid value"}


def test_malformed_json_echoes_nothing():
    response = _posting(_EveryConstraint).post(
        "/validate", content=b'{"required": the-secret-value', headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert SECRET not in response.text


# --- public_message ---------------------------------------------------------------------


class _Needs(BaseModel):
    number: int


def _unmarked():
    yield ValueError("invalid literal for int() with base 10: 'the-secret-value'")
    yield RuntimeError("postgresql://user:the-secret-value@db/internal")
    yield LookupError("the-secret-value")
    yield AppError("the-secret-value")
    try:
        _Needs(number="the-secret-value")
    except ValidationError as exc:
        yield exc
    try:
        json.loads("the-secret-value")
    except ValueError as exc:
        yield exc


class _UnmarkedApplicationError(Exception):
    __module__ = "app.domain.something"


@pytest.mark.parametrize("error", [*_unmarked(), _UnmarkedApplicationError("the-secret-value")], ids=lambda e: type(e).__name__)
def test_an_unmarked_exception_gets_the_fallback(error):
    assert public_message(error, "fallback") == "fallback"


@pytest.mark.parametrize(
    "error",
    [ClientSafeError("written"), ClientError("written"), InvalidJobTransition("written"), AIServiceGatewayError("written")],
)
def test_a_marked_exception_keeps_its_message(error):
    assert isinstance(error, ClientMessage)
    assert public_message(error, "fallback") == "written"


# --- evidence is measured, not merely numeric ---------------------------------------------


@pytest.mark.parametrize("bad", [True, False, math.nan, math.inf, -math.inf, -1, -0.5, "5", None])
def test_a_measure_must_be_a_finite_non_negative_number(bad):
    assert safe_evidence({"characters": bad, "seconds": bad}) == {}


@pytest.mark.parametrize("good", [0, 7, 0.5])
def test_a_real_measure_is_kept(good):
    assert safe_evidence({"seconds": good}) == {"seconds": good}


@pytest.mark.parametrize("bad", [1, 0, "true", None])
def test_a_flag_must_be_a_boolean(bad):
    assert safe_evidence({"verified": bad}) == {}


def test_a_real_flag_is_kept():
    assert safe_evidence({"verified": True}) == {"verified": True}
