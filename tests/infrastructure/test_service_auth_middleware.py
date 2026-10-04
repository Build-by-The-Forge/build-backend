"""Inbound service authentication against a real Redis (C8-C11).

Set TEST_REDIS_URL (e.g. redis://127.0.0.1:6379/15). The Redis-unavailable
cases use a real client pointed at a port where nothing listens.
"""

import os
import time
from uuid import uuid4

import httpx
import pytest
from app.infrastructure.security.replay_store import REPLAY_TTL_SECONDS, RedisReplayStore
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import (
    HEADER_CONTEXT,
    HEADER_REQUEST_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    Direction,
    ServiceKeys,
    sign_request,
)
from app.middleware.service_auth import MAX_BODY_BYTES, STATE_KEY, ServiceAuthMiddleware
from fastapi import FastAPI, Request
from pydantic import BaseModel
from redis.asyncio import Redis

REDIS_URL = os.getenv("TEST_REDIS_URL")
DEAD_REDIS_URL = "redis://127.0.0.1:1/0"
needs_redis = pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")

SECRET = "test-only-ai-to-backend-secret-fedcba9876543210"
KEYS = ServiceKeys(current=SECRET)
RECEIVER = "build-backend"
PATH = "/content/ingestion/callbacks"
TENANT = "6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c"
CONTEXT = ServiceContext.for_system(tenant_id=TENANT, correlation_id="job-1:attempt-1")
UNIFORM_401 = {"error": "invalid service authentication"}


class Event(BaseModel):
    event_id: str
    stage: str


def build_app(replay_store) -> tuple[FastAPI, list[dict]]:
    calls: list[dict] = []
    app = FastAPI()

    @app.post(PATH)
    async def callback(event: Event, request: Request) -> dict:
        verified = getattr(request.state, STATE_KEY)
        calls.append({"event": event.event_id, "tenant": verified.context.tenant_id})
        return {"ok": True, "tenant": verified.context.tenant_id, "stage": event.stage}

    @app.post("/public")
    async def public(request: Request) -> dict:
        return {"length": len(await request.body())}

    app.add_middleware(
        ServiceAuthMiddleware,
        receiver=RECEIVER,
        direction=Direction.AI_TO_BACKEND,
        keys=KEYS,
        replay_store=replay_store,
        is_protected=lambda path: path.startswith("/content/ingestion/"),
    )
    return app, calls


def signed(body: bytes, *, timestamp: int | None = None, request_id: str | None = None, target=PATH):
    headers = sign_request(
        direction=Direction.AI_TO_BACKEND,
        keys=KEYS,
        method="POST",
        target=target,
        body=body,
        context=CONTEXT,
        timestamp=int(time.time()) if timestamp is None else timestamp,
        request_id=request_id,
    )
    # Content-Type is not a signed header.
    return {**headers, "Content-Type": "application/json"}


def event_body(event_id: str = "evt-1") -> bytes:
    return f'{{"event_id":"{event_id}","stage":"extracted"}}'.encode()


@pytest.fixture
async def store():
    store = RedisReplayStore.from_url(REDIS_URL, timeout_seconds=2)
    yield store
    await store.close()


@pytest.fixture
async def dead_store():
    store = RedisReplayStore.from_url(DEAD_REDIS_URL, timeout_seconds=0.5)
    yield store
    await store.close()


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend")


# --- valid -----------------------------------------------------------------------


@needs_redis
async def test_valid_signed_request_reaches_the_route_with_its_body_and_context(store):
    app, calls = build_app(store)
    body = event_body()
    async with client_for(app) as client:
        resp = await client.post(PATH, content=body, headers=signed(body))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "tenant": TENANT, "stage": "extracted"}
    assert calls == [{"event": "evt-1", "tenant": TENANT}]


@needs_redis
async def test_unprotected_paths_are_untouched(store):
    app, _ = build_app(store)
    async with client_for(app) as client:
        resp = await client.post("/public", content=b"abc")
    assert resp.json() == {"length": 3}


@needs_redis
async def test_body_of_exactly_the_limit_is_accepted(store):
    app = FastAPI()
    seen: list[int] = []

    @app.post(PATH)
    async def raw(request: Request) -> dict:
        seen.append(len(await request.body()))
        return {}

    app.add_middleware(
        ServiceAuthMiddleware,
        receiver=RECEIVER,
        direction=Direction.AI_TO_BACKEND,
        keys=KEYS,
        replay_store=store,
        is_protected=lambda path: path == PATH,
    )
    body = b"x" * MAX_BODY_BYTES
    async with client_for(app) as client:
        resp = await client.post(PATH, content=body, headers=signed(body))
    assert resp.status_code == 200
    assert seen == [MAX_BODY_BYTES]


# --- C8 stale ------------------------------------------------------------------------


@needs_redis
@pytest.mark.parametrize("offset", [-61, 61, -3600])
async def test_stale_or_future_requests_are_refused(store, offset):
    app, calls = build_app(store)
    body = event_body()
    async with client_for(app) as client:
        resp = await client.post(
            PATH, content=body, headers=signed(body, timestamp=int(time.time()) + offset)
        )
    assert (resp.status_code, resp.json()) == (401, UNIFORM_401)
    assert calls == []


# --- C9 replay ------------------------------------------------------------------------


@needs_redis
async def test_the_same_signed_request_twice_is_refused_the_second_time(store):
    app, calls = build_app(store)
    body = event_body()
    headers = signed(body)
    async with client_for(app) as client:
        first = await client.post(PATH, content=body, headers=headers)
        second = await client.post(PATH, content=body, headers=headers)
    assert first.status_code == 200
    assert (second.status_code, second.json()) == (401, UNIFORM_401)
    assert len(calls) == 1

    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        key = RedisReplayStore.key(RECEIVER, "ai-service", headers[HEADER_REQUEST_ID])
        assert await redis.get(key) == "1"
        assert 0 < await redis.ttl(key) <= REPLAY_TTL_SECONDS
    finally:
        await redis.aclose()


@needs_redis
async def test_a_reused_request_id_with_a_new_signature_is_refused(store):
    app, calls = build_app(store)
    request_id = str(uuid4())
    async with client_for(app) as client:
        first_body, second_body = event_body("evt-1"), event_body("evt-2")
        await client.post(PATH, content=first_body, headers=signed(first_body, request_id=request_id))
        resp = await client.post(
            PATH, content=second_body, headers=signed(second_body, request_id=request_id)
        )
    assert resp.status_code == 401
    assert [c["event"] for c in calls] == ["evt-1"]


@needs_redis
async def test_an_invalid_signature_does_not_burn_the_request_id(store):
    app, calls = build_app(store)
    body = event_body()
    headers = signed(body)
    async with client_for(app) as client:
        forged = await client.post(PATH, content=event_body("evt-forged"), headers=headers)
        genuine = await client.post(PATH, content=body, headers=headers)
    assert forged.status_code == 401
    assert genuine.status_code == 200
    assert [c["event"] for c in calls] == ["evt-1"]


@needs_redis
async def test_replay_keys_are_scoped_to_the_receiver(store):
    request_id = str(uuid4())
    assert await store.claim("ai-service", "build-backend", request_id) is True
    assert await store.claim(RECEIVER, "ai-service", request_id) is True
    assert await store.claim(RECEIVER, "ai-service", request_id) is False


# --- C10 malformed ------------------------------------------------------------------


@needs_redis
@pytest.mark.parametrize(
    "mutate",
    [
        lambda h: h.pop(HEADER_SIGNATURE),
        lambda h: h.pop(HEADER_CONTEXT),
        lambda h: h.update({HEADER_CONTEXT: "%%%"}),
        lambda h: h.update({HEADER_TIMESTAMP: "soon"}),
        lambda h: h.update({HEADER_REQUEST_ID: "1"}),
        lambda h: h.update({HEADER_SIGNATURE: "Bearer static-key"}),
        lambda h: h.update({"X-BUILD-Service": "build-backend"}),
    ],
    ids=["no-signature", "no-context", "bad-context", "bad-ts", "bad-id", "bearer", "wrong-sender"],
)
async def test_malformed_requests_get_the_uniform_401(store, mutate):
    app, calls = build_app(store)
    body = event_body()
    headers = signed(body)
    mutate(headers)
    async with client_for(app) as client:
        resp = await client.post(PATH, content=body, headers=headers)
    assert (resp.status_code, resp.json()) == (401, UNIFORM_401)
    assert calls == []


@needs_redis
async def test_unsigned_request_with_a_bearer_token_is_refused(store):
    app, calls = build_app(store)
    async with client_for(app) as client:
        resp = await client.post(
            PATH, content=event_body(), headers={"Authorization": f"Bearer {SECRET}"}
        )
    assert (resp.status_code, resp.json()) == (401, UNIFORM_401)
    assert calls == []


@needs_redis
async def test_query_added_after_signing_is_refused(store):
    app, calls = build_app(store)
    body = event_body()
    async with client_for(app) as client:
        resp = await client.post(PATH + "?tenant_id=other", content=body, headers=signed(body))
    assert resp.status_code == 401
    assert calls == []


@needs_redis
async def test_signed_query_is_accepted(store):
    app, calls = build_app(store)
    body = event_body()
    async with client_for(app) as client:
        resp = await client.post(
            PATH + "?a=1&b=x%20y", content=body, headers=signed(body, target=PATH + "?a=1&b=x%20y")
        )
    assert resp.status_code == 200
    assert len(calls) == 1


# --- oversized body ------------------------------------------------------------------


@needs_redis
async def test_declared_oversized_body_is_refused_before_reading(store):
    app, calls = build_app(store)
    body = b"x" * (MAX_BODY_BYTES + 1)
    async with client_for(app) as client:
        resp = await client.post(PATH, content=body, headers=signed(body))
    assert resp.status_code == 413
    assert calls == []


async def _call_raw(app, headers: dict[str, str], chunks: list[bytes]):
    """Drive the ASGI app directly with a streamed body (no Content-Length)
    and record how much of it the middleware consumed."""
    consumed: list[int] = []
    sent: list[dict] = []
    pending = list(chunks)

    async def receive():
        if not pending:
            return {"type": "http.disconnect"}
        chunk = pending.pop(0)
        consumed.append(len(chunk))
        return {"type": "http.request", "body": chunk, "more_body": bool(pending)}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": PATH,
        "raw_path": PATH.encode(),
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 1),
        "server": ("backend", 80),
    }
    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, consumed


@needs_redis
async def test_streamed_oversized_body_is_cut_off_at_the_limit(store):
    app, calls = build_app(store)
    chunk = b"x" * (256 * 1024)
    chunks = [chunk] * 16  # 4 MiB offered, no Content-Length
    status, consumed = await _call_raw(app, signed(b"".join(chunks)), chunks)
    assert status == 413
    assert sum(consumed) <= MAX_BODY_BYTES + len(chunk)  # stopped at the limit
    assert len(consumed) < len(chunks)
    assert calls == []


@needs_redis
async def test_malformed_headers_are_refused_before_the_body_is_read(store):
    app, calls = build_app(store)
    headers = signed(b"x")
    del headers[HEADER_SIGNATURE]
    status, consumed = await _call_raw(app, headers, [b"x" * 1024] * 4)
    assert status == 401
    assert consumed == []
    assert calls == []


@needs_redis
async def test_streamed_body_within_the_limit_is_accepted(store):
    app, calls = build_app(store)
    body = event_body()
    chunks = [body[:10], body[10:20], body[20:]]
    status, consumed = await _call_raw(app, signed(body), chunks)
    assert status == 200
    assert sum(consumed) == len(body)
    assert len(calls) == 1


# --- C11 Redis unavailable -----------------------------------------------------------


async def test_redis_unavailable_fails_closed_with_503(dead_store):
    app, calls = build_app(dead_store)
    body = event_body()
    async with client_for(app) as client:
        resp = await client.post(PATH, content=body, headers=signed(body))
    assert (resp.status_code, resp.json()) == (503, {"error": "service temporarily unavailable"})
    assert calls == []


async def test_redis_unavailable_still_answers_401_for_a_bad_signature(dead_store):
    app, calls = build_app(dead_store)
    body = event_body()
    async with client_for(app) as client:
        resp = await client.post(PATH, content=event_body("tampered"), headers=signed(body))
    assert resp.status_code == 401
    assert calls == []
