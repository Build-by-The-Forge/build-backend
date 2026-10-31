"""Migrations 0025 and 0026 on real rows.

The migrated-schema checks run on empty tables, so a backfill's logic was never
exercised. This goes back to before both, leaves real rows there, and upgrades.
Run in a subprocess: Alembic's env.py runs its own event loop.
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.session import SessionLocal, engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

ROOT = Path(__file__).resolve().parents[1]


def _alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=os.environ, check=True, capture_output=True)


async def test_existing_rows_get_a_deadline_and_the_practice_defaults(client):
    registered = await client.post(
        "/identity/users", json={"email": f"mig-{uuid4()}@example.com", "password": "Correct-Horse-Battery-9"}
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["data"]["id"]
    tag = uuid4().hex[:8]
    tenant_id, faculty_id, department_id, course_id, assessment_id, attempt_id = (str(uuid4()) for _ in range(6))
    now = datetime.now(timezone.utc)
    started = now - timedelta(hours=2)

    await engine.dispose()
    _alembic("downgrade", "0024")
    try:
        async with SessionLocal() as session:
            values = {
                "tenant": tenant_id,
                "faculty": faculty_id,
                "department": department_id,
                "course": course_id,
                "assessment": assessment_id,
                "attempt": attempt_id,
                "user": user_id,
                "now": now,
                "started": started,
                "tag": tag,
            }
            for statement in (
                "INSERT INTO tenants (id, name, slug, status, created_at, updated_at)"
                " VALUES (:tenant, 'M', 'mig-' || :tag, 'active', :now, :now)",
                "INSERT INTO faculties (id, tenant_id, name, slug, status, created_at, updated_at)"
                " VALUES (:faculty, :tenant, 'M', 'f-' || :tag, 'active', :now, :now)",
                "INSERT INTO departments (id, tenant_id, faculty_id, name, slug, code, status, created_at, updated_at)"
                " VALUES (:department, :tenant, :faculty, 'M', 'd-' || :tag, 'D' || :tag, 'active', :now, :now)",
                "INSERT INTO courses (id, tenant_id, department_id, code, title, slug, credit_units, level, semester,"
                " status, created_at, updated_at)"
                " VALUES (:course, :tenant, :department, 'C' || :tag, 'M', 'c-' || :tag, 3, 100, 1, 'published', :now, :now)",
                "INSERT INTO assessments (id, tenant_id, course_id, title, instructions, duration_minutes, passing_score,"
                " status, created_at, updated_at)"
                " VALUES (:assessment, :tenant, :course, 'M', 'x', 45, 0, 'published', :now, :now)",
                "INSERT INTO assessment_attempts"
                " (id, tenant_id, assessment_id, user_id, status, started_at, created_at, updated_at)"
                " VALUES (:attempt, :tenant, :assessment, :user, 'in_progress', :started, :now, :now)",
            ):
                await session.execute(text(statement), values)
            await session.commit()
    finally:
        await engine.dispose()
        _alembic("upgrade", "head")

    from app.infrastructure.db.models.assessment import AssessmentAttemptModel, AssessmentModel

    async with SessionLocal() as session:
        attempt = (await session.scalars(select(AssessmentAttemptModel).where(AssessmentAttemptModel.id == attempt_id))).one()
        assessment = (await session.scalars(select(AssessmentModel).where(AssessmentModel.id == assessment_id))).one()

    assert attempt.expires_at == started + timedelta(minutes=45)
    assert attempt.status == "in_progress"
    assert assessment.attempt_kind == "practice"
    assert assessment.max_attempts is None
    assert assessment.retake_after_submission is True
    assert assessment.result_visibility == "immediate"
    assert assessment.feedback_timing == "immediate"
    assert assessment.scoring_policy == "best"
