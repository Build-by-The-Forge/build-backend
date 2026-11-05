"""Only the one-active-job rule becomes ACTIVE_JOB_EXISTS; any other
integrity error still fails loudly."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.infrastructure.content.job_repositories import is_active_job_conflict


def _error(message: str) -> IntegrityError:
    return IntegrityError("UPDATE content_ingestion_jobs ...", {}, Exception(message))


@pytest.mark.parametrize(
    "message",
    [
        'duplicate key value violates unique constraint "ux_content_ingestion_jobs_active_asset"',
        "UNIQUE constraint failed: content_ingestion_jobs.asset_id",
    ],
)
def test_the_active_job_index_is_recognised(message):
    assert is_active_job_conflict(_error(message))


@pytest.mark.parametrize(
    "message",
    [
        'duplicate key value violates unique constraint "uq_content_ingestion_jobs_asset_run"',
        "UNIQUE constraint failed: content_ingestion_jobs.asset_id, content_ingestion_jobs.run_number",
        'insert or update on table "content_ingestion_jobs" violates foreign key constraint',
    ],
)
def test_other_integrity_errors_are_not(message):
    assert not is_active_job_conflict(_error(message))
