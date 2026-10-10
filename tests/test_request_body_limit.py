"""Global request body limit (plan §8.4, M6)."""

import httpx
import pytest
from app.main import app
from app.middleware.body_limit import RequestBodyLimitMiddleware
from fastapi import FastAPI, Request


def tiny_app(limit: int = 100) -> FastAPI:
    inner = FastAPI()

    @inner.post("/echo")
    async def echo(request: Request) -> dict:
        return {"size": len(await request.body())}

    inner.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=limit)
    return inner


async def post(application, content, headers=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://t") as client:
        return await client.post("/echo", content=content, headers=headers or {})


async def test_a_body_within_the_limit_is_served():
    response = await post(tiny_app(), b"x" * 100)
    assert (response.status_code, response.json()) == (200, {"size": 100})


async def test_a_declared_oversized_body_is_413_before_the_app_runs():
    response = await post(tiny_app(), b"x" * 101)
    assert response.status_code == 413
    assert response.json()["meta"]["error"] == "request body too large"


async def test_a_streamed_body_that_grows_past_the_limit_is_413():
    async def chunks():
        for _ in range(5):
            yield b"x" * 40

    response = await post(tiny_app(), chunks())
    assert response.status_code == 413


@pytest.mark.parametrize("path", ["/identity/users", "/content/ingestion/callbacks", "/ai/chat"])
def test_the_real_app_refuses_oversized_bodies_everywhere(path):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post(path, content=b"{" + b" " * (1024 * 1024 + 1) + b"}", headers={"Content-Type": "application/json"})
    assert response.status_code == 413
