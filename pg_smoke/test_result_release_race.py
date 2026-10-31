"""Concurrent releases on PostgreSQL: one row, and every caller gets that row."""

import asyncio

import pytest
from sqlalchemy import func, select

from app.application.assessment.assessment_service import AssessmentService
from app.bootstrap.container import build_container
from app.db.session import SessionLocal
from app.infrastructure.db.models.assessment import AssessmentResultReleaseModel
from pg_smoke.test_attempt_policy_race import _assessment, _student

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_concurrent_releases_leave_one_row(client):
    user_id = await _student(client)
    tenant_id, assessment_id = await _assessment()
    service = build_container().get(AssessmentService)

    releases = await asyncio.gather(*(service.release_results(assessment_id, tenant_id, user_id) for _ in range(5)))

    assert len({release.released_at for release in releases}) == 1
    async with SessionLocal() as session:
        statement = select(func.count()).where(AssessmentResultReleaseModel.assessment_id == assessment_id)
        assert (await session.execute(statement)).scalar_one() == 1
