"""received_upload: the body streamed, hashed and limited, with its
temporary file removed on every path."""

import asyncio
import hashlib
import tempfile

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.content import upload_body
from app.api.content.upload_body import received_upload
from app.application.content.upload import UploadReadTimeoutError, UploadTooLargeError


def app_with(max_bytes: int = 100, timeout_seconds: float = 2.0, fail_inside: bool = False) -> FastAPI:
    application = FastAPI()

    @application.post("/u")
    async def receive(request: Request) -> dict:
        try:
            async with received_upload(request, max_bytes=max_bytes, timeout_seconds=timeout_seconds) as body:
                if fail_inside:
                    raise RuntimeError("the caller failed")
                content = body.file.read()
                return {"size": body.size_bytes, "sha256": body.sha256, "head": body.head.hex(), "bytes": len(content)}
        except (UploadTooLargeError, UploadReadTimeoutError, RuntimeError) as exc:
            return {"error": type(exc).__name__}

    return application


@pytest.fixture(autouse=True)
def track_spools(monkeypatch):
    """Record every spooled file the reader opens, to check it is closed."""
    created = []
    real = tempfile.SpooledTemporaryFile

    def tracked(*args, **kwargs):
        spool = real(*args, **kwargs)
        created.append(spool)
        return spool

    monkeypatch.setattr(upload_body.tempfile, "SpooledTemporaryFile", tracked)
    return created


async def post(application, content):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://t") as client:
        return await client.post("/u", content=content)


async def test_the_body_is_hashed_counted_and_rewound(track_spools):
    data = b"%PDF-1.7 " + b"x" * 50

    response = await post(app_with(), data)

    assert response.json()["size"] == len(data) == response.json()["bytes"]
    assert response.json()["sha256"] == hashlib.sha256(data).hexdigest()
    assert bytes.fromhex(response.json()["head"]) == data[:8]
    assert all(spool.closed for spool in track_spools)


async def test_a_streamed_body_over_the_limit_is_refused_without_content_length(track_spools):
    async def chunks():
        for _ in range(5):
            yield b"y" * 40  # 200 bytes, no Content-Length

    response = await post(app_with(max_bytes=100), chunks())

    assert response.json() == {"error": "UploadTooLargeError"}
    assert all(spool.closed for spool in track_spools)


async def test_a_slow_body_hits_the_read_deadline(track_spools):
    async def slow():
        yield b"%PDF"
        await asyncio.sleep(1)
        yield b"-1.7"

    response = await post(app_with(timeout_seconds=0.2), slow())

    assert response.json() == {"error": "UploadReadTimeoutError"}
    assert all(spool.closed for spool in track_spools)


async def test_the_temporary_file_is_removed_when_the_caller_fails(track_spools):
    response = await post(app_with(fail_inside=True), b"%PDF-1.7 data")

    assert response.json() == {"error": "RuntimeError"}
    assert track_spools and all(spool.closed for spool in track_spools)
