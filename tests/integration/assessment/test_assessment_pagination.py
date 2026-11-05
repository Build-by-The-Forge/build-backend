"""Both assessment lists against the contract (M3-E, G-10): paged and counted
in SQL, newest first then by id, with attempts_used for the page only."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.db.session import SessionLocal
from app.infrastructure.db.models.assessment import AssessmentAttemptModel, AssessmentModel
from tests.integration.assessment.test_assessment_visibility import assessment_with_question

SAME_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def published_assessments(client, count: int):
    """One tenant with `count` published assessments, all created at the same
    instant, so only the id can order them."""
    lecturer, student, first_id, question_id = await assessment_with_question(client, published=True)
    course_id = client.get(f"/assessment/staff/assessments/{first_id}", headers=lecturer).json()["data"]["course_id"]
    ids = [first_id]
    for n in range(count - 1):
        created = client.post(
            "/assessment/assessments",
            headers=lecturer,
            json={"course_id": course_id, "title": f"Paged {n}", "instructions": "Answer.", "duration_minutes": 30},
        )
        assert created.status_code == 201, created.text
        assessment_id = created.json()["data"]["id"]
        added = client.post(
            f"/assessment/assessments/{assessment_id}/questions", headers=lecturer, json={"question_id": question_id}
        )
        assert added.status_code == 200, added.text
        assert client.post(f"/assessment/assessments/{assessment_id}/publish", headers=lecturer).status_code == 200
        ids.append(assessment_id)
    async with SessionLocal() as session:
        await session.execute(update(AssessmentModel).where(AssessmentModel.id.in_(ids)).values(created_at=SAME_TIME))
        await session.commit()
    return lecturer, student, course_id, ids


def listed(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["data"]]


@pytest.mark.asyncio
async def test_assessment_pages_cover_everything_once_in_contract_order_with_the_true_total(client):
    _, student, _, ids = await published_assessments(client, 5)

    seen: list[str] = []
    for offset in (0, 2, 4):
        response = client.get(f"/assessment/assessments?limit=2&offset={offset}", headers=student)
        seen += listed(response)
        assert response.json()["meta"]["pagination"] == {"total": 5, "limit": 2, "offset": offset}

    # Same created_at for all five: the id decides, descending.
    assert seen == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_newer_assessments_come_first(client):
    _, student, _, ids = await published_assessments(client, 3)
    async with SessionLocal() as session:
        await session.execute(
            update(AssessmentModel)
            .where(AssessmentModel.id == ids[0])
            .values(created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    assert listed(client.get("/assessment/assessments", headers=student))[0] == ids[0]


@pytest.mark.asyncio
async def test_the_course_filter_narrows_the_page_and_the_total(client):
    _, student, course_id, ids = await published_assessments(client, 3)

    response = client.get(f"/assessment/assessments?course_id={course_id}&limit=2", headers=student)
    assert len(listed(response)) == 2
    assert response.json()["meta"]["pagination"]["total"] == 3

    for unknown in ("", "not-a-course", str(uuid4())):
        empty = client.get("/assessment/assessments", headers=student, params={"course_id": unknown})
        assert listed(empty) == [], unknown
        assert empty.json()["meta"]["pagination"]["total"] == 0, unknown


@pytest.mark.asyncio
async def test_drafts_are_neither_listed_nor_counted(client):
    lecturer, student, course_id, _ = await published_assessments(client, 2)
    draft = client.post(
        "/assessment/assessments",
        headers=lecturer,
        json={"course_id": course_id, "title": "Draft", "instructions": "Answer.", "duration_minutes": 30},
    )
    assert draft.status_code == 201, draft.text

    response = client.get("/assessment/assessments", headers=student)
    assert draft.json()["data"]["id"] not in listed(response)
    assert response.json()["meta"]["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_attempt_pages_cover_everything_once_in_contract_order_with_the_true_total(client):
    _, student, _, ids = await published_assessments(client, 3)
    started = []
    for assessment_id in ids:
        response = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
        assert response.status_code in (200, 201), response.text
        started.append(response.json()["data"]["id"])
    async with SessionLocal() as session:
        await session.execute(
            update(AssessmentAttemptModel).where(AssessmentAttemptModel.id.in_(started)).values(created_at=SAME_TIME)
        )
        await session.commit()

    seen: list[str] = []
    for offset in (0, 2):
        response = client.get(f"/assessment/attempts?limit=2&offset={offset}", headers=student)
        seen += listed(response)
        assert response.json()["meta"]["pagination"] == {"total": 3, "limit": 2, "offset": offset}
    assert seen == sorted(started, reverse=True)


@pytest.mark.asyncio
async def test_attempts_used_is_reported_for_the_page(client):
    _, student, _, ids = await published_assessments(client, 3)
    assert client.post(f"/assessment/assessments/{ids[0]}/attempts", headers=student).status_code in (200, 201)

    page = client.get("/assessment/assessments?limit=100", headers=student).json()["data"]
    used = {item["id"]: item["attempts_used"] for item in page}
    assert used == {ids[0]: 1, ids[1]: 0, ids[2]: 0}
    one = client.get(f"/assessment/assessments/{ids[0]}", headers=student).json()["data"]
    assert one["attempts_used"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/assessment/assessments", "/assessment/attempts"])
@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "limit=-1", "limit=many", "offset=-1", "offset=first", "offset=2147483648"],
)
async def test_invalid_limits_and_offsets_are_refused(client, path, query):
    _, student, _, _ = await published_assessments(client, 1)

    response = client.get(f"{path}?{query}", headers=student)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/assessment/assessments", "/assessment/attempts"])
async def test_defaults_the_largest_offset_and_a_page_past_the_end(client, path):
    _, student, _, _ = await published_assessments(client, 1)

    default = client.get(path, headers=student).json()["meta"]["pagination"]
    assert (default["limit"], default["offset"]) == (50, 0)
    assert client.get(f"{path}?limit=100", headers=student).status_code == 200
    past = client.get(f"{path}?offset=2147483647", headers=student)
    assert listed(past) == []
    assert past.json()["meta"]["pagination"]["total"] == default["total"]


@pytest.mark.asyncio
async def test_a_nul_in_the_course_filter_is_refused(client):
    _, student, _, _ = await published_assessments(client, 1)

    response = client.get("/assessment/assessments?course_id=a%00b", headers=student)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
