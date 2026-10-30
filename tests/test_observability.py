import logging

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.exceptions import http_exception_handler
from app.core.metrics import metrics_payload
from app.infrastructure.unit_of_work import UnitOfWork


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


def test_p3_6_worker_metrics_are_exposed():
    payload = metrics_payload()

    for metric in (
        b"build_backend_content_jobs_dispatched_total",
        b"build_backend_content_dispatch_failures_total",
        b"build_backend_content_retries_scheduled_total",
        b"build_backend_content_terminal_failures_total",
        b"build_backend_content_recoveries_total",
        b"build_backend_content_in_flight_cap_hits_total",
        b"build_backend_content_orphan_objects_deleted_total",
        b"build_backend_content_orphan_objects_kept_total",
        b"build_backend_content_jobs_due",
        b"build_backend_content_oldest_due_job_age_seconds",
    ):
        assert metric in payload
