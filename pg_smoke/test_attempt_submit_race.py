"""Concurrent submits on PostgreSQL: the row lock lets one grade the attempt,
and the other gets the same submitted attempt rather than an error."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.application.assessment.attempt_service import AttemptService
from app.bootstrap.container import build_container
from app.db.session import SessionLocal
from app.infrastructure.db.models.assessment import AssessmentAttemptResultModel, AssessmentModel
from tests.integration.assessment.test_assessment_api import course_id_for_tenant
from tests.integration.assessment.test_question_api import seed_tenant_context

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_concurrent_submits_grade_once(client):
    registered = await client.post(
        "/identity/users", json={"email": f"race-{uuid4()}@example.com", "password": "Correct-Horse-Battery-9"}
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["data"]["id"]
    tenant_id, *_ = await seed_tenant_context(user_id, "student")
    assessment_id = str(uuid4())
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add(
            AssessmentModel(
                id=assessment_id,
                tenant_id=tenant_id,
                course_id=await course_id_for_tenant(tenant_id),
                title="Race",
                instructions="Answer.",
                duration_minutes=30,
                passing_score=0,
                status="published",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    service = build_container().get(AttemptService)
    attempt = await service.start_attempt(assessment_id, tenant_id, user_id)
    results = await asyncio.gather(
        *(service.submit_attempt(attempt.id, tenant_id, user_id) for _ in range(5)), return_exceptions=True
    )

    assert [r for r in results if isinstance(r, BaseException)] == []
    assert {r.status.value for r in results} == {"submitted"}
    assert sum(r.newly_submitted for r in results) == 1
    async with SessionLocal() as session:
        graded = await session.scalar(
            select(func.count())
            .select_from(AssessmentAttemptResultModel)
            .where(AssessmentAttemptResultModel.attempt_id == attempt.id)
        )
    assert graded == 1
