import logging

import pytest
from app.core.exceptions import http_exception_handler
from app.core.metrics import metrics_payload
from app.infrastructure.unit_of_work import UnitOfWork
from fastapi import HTTPException
from starlette.requests import Request


class FailingSession:
    async def commit(self) -> None:
        raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class RollbackSession:
    def __init__(self) -> None:
        self.rollback_called = False

    async def commit(self) -> None:
        raise AssertionError("commit must not run during rollback")

    async def rollback(self) -> None:
        self.rollback_called = True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_unit_of_work_logs_commit_failure(caplog):
    caplog.set_level(logging.ERROR)

    with pytest.raises(RuntimeError, match="commit failed"):
        async with UnitOfWork(FailingSession()):
            pass

    assert "unit_of_work_commit_failed" in caplog.text


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_and_logs_operation_failure(caplog):
    caplog.set_level(logging.ERROR)
    session = RollbackSession()

    with pytest.raises(RuntimeError, match="operation failed"):
        async with UnitOfWork(session):
            raise RuntimeError("operation failed")

    assert session.rollback_called is True
    assert "unit_of_work_rollback" in caplog.text


@pytest.mark.asyncio
async def test_http_exception_preserves_request_id_and_records_metric():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/missing",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.request_id = "request-test-123"

    response = await http_exception_handler(request, HTTPException(404))
    assert response.status_code == 404
    assert response.body.find(b"request-test-123") >= 0
    assert b"build_backend_errors_total" in metrics_payload()
