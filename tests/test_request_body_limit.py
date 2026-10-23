"""Global request body limit (plan §8.4, M6)."""

import httpx
import pytest
from fastapi import FastAPI, Request

from app.main import app
from app.middleware.body_limit import RequestBodyLimitMiddleware, RouteBodyLimit


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


# --- per-route limits (document uploads, P3-1 PR 2) ----------------------------------------


def routed_app(global_limit: int = 100, upload_limit: int = 1000) -> FastAPI:
    inner = FastAPI()

    @inner.post("/sources/{source_id}/upload")
    async def upload(source_id: str, request: Request) -> dict:
        return {"size": len(await request.body())}

    @inner.put("/sources/{source_id}/upload")
    async def upload_put(source_id: str, request: Request) -> dict:
        return {"size": len(await request.body())}

    @inner.post("/sources/{source_id}/upload/extra")
    async def other(source_id: str, request: Request) -> dict:
        return {"size": len(await request.body())}

    inner.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=global_limit,
        route_limits=[RouteBodyLimit("POST", r"/sources/[^/]+/upload", upload_limit)],
    )
    return inner


async def send_to(application, method, path, content):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://t") as client:
        return await client.request(method, path, content=content)


async def test_the_route_limit_admits_a_body_above_the_global_limit():
    response = await send_to(routed_app(), "POST", "/sources/s1/upload", b"x" * 1000)
    assert (response.status_code, response.json()) == (200, {"size": 1000})


async def test_the_route_limit_still_caps_its_route_declared_and_streamed():
    declared = await send_to(routed_app(), "POST", "/sources/s1/upload", b"x" * 1001)

    async def chunks():
        for _ in range(11):
            yield b"x" * 100

    streamed = await send_to(routed_app(), "POST", "/sources/s1/upload", chunks())

    assert (declared.status_code, streamed.status_code) == (413, 413)


@pytest.mark.parametrize(
    ("method", "path"),
    [("PUT", "/sources/s1/upload"), ("POST", "/sources/s1/upload/extra"), ("POST", "/echo")],
)
async def test_other_methods_and_paths_keep_the_global_limit(method, path):
    response = await send_to(routed_app(), method, path, b"x" * 101)

    assert response.status_code == 413
