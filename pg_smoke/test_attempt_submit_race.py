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
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import DepartmentModel, FacultyModel, TenantModel

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _published_assessment() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    stamps = {"status": "active", "created_at": now, "updated_at": now}
    tenant_id, faculty_id, department_id, course_id, assessment_id = (str(uuid4()) for _ in range(5))
    tag = uuid4().hex[:8]
    rows = [
        TenantModel(id=tenant_id, name="Race", slug=f"race-{tag}", **stamps),
        FacultyModel(id=faculty_id, tenant_id=tenant_id, name="Race", slug=f"f-{tag}", **stamps),
        DepartmentModel(
            id=department_id, tenant_id=tenant_id, faculty_id=faculty_id, name="Race", slug=f"d-{tag}", code=f"D{tag}", **stamps
        ),
        CourseModel(
            id=course_id,
            tenant_id=tenant_id,
            department_id=department_id,
            code=f"C{tag}",
            title="Race",
            slug=f"c-{tag}",
            credit_units=3,
            level=100,
            semester=1,
            status="published",
            created_at=now,
            updated_at=now,
        ),
        AssessmentModel(
            id=assessment_id,
            tenant_id=tenant_id,
            course_id=course_id,
            title="Race",
            instructions="Answer.",
            duration_minutes=30,
            passing_score=0,
            status="published",
            created_at=now,
            updated_at=now,
        ),
    ]
    async with SessionLocal() as session:
        for row in rows:  # one at a time, parents first, for the foreign keys
            session.add(row)
            await session.flush()
        await session.commit()
    return tenant_id, assessment_id


async def test_concurrent_submits_grade_once(client):
    registered = await client.post(
        "/identity/users", json={"email": f"race-{uuid4()}@example.com", "password": "Correct-Horse-Battery-9"}
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["data"]["id"]
    tenant_id, assessment_id = await _published_assessment()

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
