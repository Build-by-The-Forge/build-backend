import pytest
from fastapi import HTTPException
from structlog.testing import capture_logs

from app.core.exceptions import AppError
from app.infrastructure.unit_of_work import UnitOfWork


class FakeSession:
    async def rollback(self):
        pass

    async def commit(self):
        pass

    async def close(self):
        pass


async def _fail_inside(exc):
    with capture_logs() as logs:
        with pytest.raises(type(exc)):
            async with UnitOfWork(FakeSession()):
                raise exc
    return [entry for entry in logs if entry["event"] == "unit_of_work_rollback"]


@pytest.mark.parametrize(
    "exc",
    [AppError("invalid credentials", status_code=401), HTTPException(status_code=403, detail="nope")],
)
async def test_client_errors_roll_back_at_info_without_their_message(exc):
    (entry,) = await _fail_inside(exc)

    assert entry["log_level"] == "info"
    assert "exception" not in entry


@pytest.mark.parametrize("exc", [RuntimeError("database exploded"), AppError("boom", status_code=500)])
async def test_unexpected_errors_still_roll_back_at_error(exc):
    (entry,) = await _fail_inside(exc)

    assert entry["log_level"] == "error"
    assert entry["exception"] == str(exc)
