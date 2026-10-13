"""M5 AI contracts on the real stack (docs/phase1-m5-ai-contracts.md §6).

M5-3 structured question generation through the backend; M5-4 a submitted
attempt updates the student's learning memory and only theirs; M5-5 the
memory routes refuse identity in the body and a missing permission.
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest

from boundary.conftest import jbytes, to_ai, user_context

BACKEND_APP_DSN = os.environ.get("BOUNDARY_BACKEND_APP_DSN", "")


# --- M5-3 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("question_type", ["mcq", "true_false"])
def test_m5_3_generated_questions_arrive_structured(backend, tenant_a, question_type):
    response = backend.post(
        "/ai/generate-questions",
        json={"topic": "cells", "count": 3, "difficulty": "easy", "question_type": question_type},
        headers=tenant_a.h("lecturer"),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["discarded"] == 0
    assert len(data["questions"]) == 3
    for question in data["questions"]:
        assert question["question_type"] == question_type
        assert question["difficulty"] == "easy"
        assert sum(o["is_correct"] for o in question["options"]) == 1
        assert len(question["options"]) == (2 if question_type == "true_false" else 4)


# --- M5-4 ---------------------------------------------------------------------------------


async def _seed_department(tenant_id: str) -> str:
    """Faculties and departments have no API yet; the rest is created over HTTP."""
    connection = await asyncpg.connect(BACKEND_APP_DSN)
    now = datetime.now(timezone.utc)
    faculty_id, department_id = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        await connection.execute(
            "INSERT INTO faculties (id, tenant_id, name, slug, status, created_at, updated_at)"
            " VALUES ($1, $2, 'Boundary Faculty', $3, 'active', $4, $4)",
            faculty_id,
            tenant_id,
            f"fac-{faculty_id[:8]}",
            now,
        )
        await connection.execute(
            "INSERT INTO departments (id, tenant_id, faculty_id, name, slug, code, status, created_at, updated_at)"
            " VALUES ($1, $2, $3, 'Boundary Department', $4, $5, 'active', $6, $6)",
            department_id,
            tenant_id,
            faculty_id,
            f"dep-{department_id[:8]}",
            f"D{department_id[:7].upper()}",
            now,
        )
    finally:
        await connection.close()
    return department_id


@pytest.fixture(scope="module")
def published_assessment(backend, tenant_a):
    h = tenant_a.h("lecturer")
    department_id = asyncio.run(_seed_department(tenant_a.tenant_id))
    marker = uuid.uuid4().hex[:6]
    course = backend.post(
        "/catalogue/courses/",
        json={
            "department_id": department_id,
            "code": f"BND{marker.upper()}",
            "title": "Boundary Biology",
            "slug": f"bnd-bio-{marker}",
            "credit_units": 3,
            "level": 100,
            "semester": 1,
        },
        headers=h,
    )
    assert course.status_code == 201, course.text
    course_id = course.json()["data"]["id"]
    topic_title = f"Osmosis {marker}"
    topic = backend.post(
        f"/catalogue/courses/{course_id}/topics",
        json={"title": topic_title, "slug": f"osmosis-{marker}"},
        headers=h,
    )
    assert topic.status_code == 201, topic.text
    topic_id = topic.json()["data"]["id"]

    assessment = backend.post(
        "/assessment/assessments",
        json={"course_id": course_id, "title": "Boundary quiz", "instructions": "x", "duration_minutes": 10},
        headers=h,
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["data"]["id"]
    for i in range(2):
        question = backend.post(
            "/assessment/questions",
            json={
                "topic_id": topic_id,
                "question_type": "mcq",
                "prompt": f"Boundary Q{i}?",
                "options": [
                    {"text": "Wrong", "display_order": 1, "is_correct": False},
                    {"text": "Right", "display_order": 2, "is_correct": True},
                ],
            },
            headers=h,
        )
        assert question.status_code == 201, question.text
        added = backend.post(
            f"/assessment/assessments/{assessment_id}/questions",
            json={"question_id": question.json()["data"]["id"]},
            headers=h,
        )
        assert added.status_code == 200, added.text
    published = backend.post(f"/assessment/assessments/{assessment_id}/publish", headers=h)
    assert published.status_code == 200, published.text
    return assessment_id, topic_title


def memory_of(backend, headers, topic):
    response = backend.get("/ai/memory", params={"topic": topic}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def test_m5_4_a_submitted_attempt_updates_only_the_students_memory(backend, tenant_a, tenant_b, published_assessment):
    assessment_id, topic = published_assessment
    student = tenant_a.h("student")
    started = backend.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["id"]
    questions = backend.get(f"/assessment/attempts/{attempt_id}/questions", headers=student).json()["data"]["questions"]
    for question, position in zip(questions, (1, 0), strict=True):  # one right, one wrong
        saved = backend.put(
            f"/assessment/attempts/{attempt_id}/answers/{question['assessment_question_id']}",
            json={"selected_option_index": position},
            headers=student,
        )
        assert saved.status_code in (200, 201), saved.text
    assert backend.post(f"/assessment/attempts/{attempt_id}/submit", headers=student).status_code == 200

    deadline = time.time() + 15  # the report runs after the response
    items = memory_of(backend, student, topic)
    while not items and time.time() < deadline:
        time.sleep(0.3)
        items = memory_of(backend, student, topic)
    # 0.5 start, +0.1 right, -0.05 wrong (in the scored order) = 0.55.
    assert items == [{"topic": topic, "mastery_score": pytest.approx(0.55), "attempts": 2}]

    assert memory_of(backend, tenant_a.h("lecturer"), topic) == []  # another user
    assert memory_of(backend, tenant_b.h("lecturer"), topic) == []  # another tenant


# --- M5-5 ---------------------------------------------------------------------------------

UPSERT, QUERY = "/v1/ai/memory/upsert", "/v1/ai/memory/query"
UPSERT_BODY = {"observations": [{"topic": "x", "correct": True}]}


@pytest.mark.parametrize("field", ["tenant_id", "user_id"])
@pytest.mark.parametrize(
    "path,body,permission",
    [(QUERY, {}, "ai.use"), (UPSERT, UPSERT_BODY, "assessment.attempt.submit")],
)
def test_m5_5_memory_routes_refuse_identity_in_the_body(ai, path, body, permission, field):
    raw = jbytes({**body, field: str(uuid.uuid4())})
    context = user_context(str(uuid.uuid4()), str(uuid.uuid4()), [permission])
    assert ai.post(path, content=raw, headers=to_ai("POST", path, raw, context)).status_code == 422


@pytest.mark.parametrize(
    "path,body,permission",
    [(QUERY, {}, "assessment.attempt.submit"), (UPSERT, UPSERT_BODY, "ai.use")],
)
def test_m5_5_memory_routes_need_their_own_permission(ai, path, body, permission):
    raw = jbytes(body)
    context = user_context(str(uuid.uuid4()), str(uuid.uuid4()), [permission])
    assert ai.post(path, content=raw, headers=to_ai("POST", path, raw, context)).status_code == 403


def test_m5_5_memory_routes_refuse_unsigned_requests(ai):
    assert ai.post(UPSERT, json=UPSERT_BODY).status_code == 401
    assert ai.post(QUERY, json={}, headers={"Authorization": "Bearer x"}).status_code == 401
