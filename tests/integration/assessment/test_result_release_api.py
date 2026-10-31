"""Result release, feedback timing and the standing attempt over HTTP."""

from itertools import product
from uuid import uuid4

import pytest

from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_attempt_policy_api import lecturer_and_draft
from tests.integration.assessment.test_question_api import register_and_authenticate

VISIBILITIES = ["immediate", "after_release"]
TIMINGS = ["immediate", "after_final_attempt", "after_release", "never"]


def policy(visibility="immediate", timing="immediate", *, max_attempts=2, scoring="best"):
    return {
        "kind": "formal",
        "max_attempts": max_attempts,
        "retake_after_submission": max_attempts != 1,
        "result_visibility": visibility,
        "feedback_timing": timing,
        "scoring_policy": scoring,
    }


async def published(client, attempt_policy):
    lecturer, tenant_id, slug, assessment_id = await lecturer_and_draft(client, attempt_policy)
    assert client.post(f"/assessment/assessments/{assessment_id}/publish", headers=lecturer).status_code == 200
    student_id, token = await register_and_authenticate(client, f"rel-stu-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    return lecturer, headers(token, slug), assessment_id


def take(client, student, assessment_id, *, right=True):
    """One finalized attempt on the one question."""
    attempt_id = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student).json()["data"]["id"]
    [question] = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student).json()["data"]["questions"]
    saved = client.put(
        f"/assessment/attempts/{attempt_id}/answers/{question['assessment_question_id']}",
        json={"selected_option_index": 1 if right else 0},
        headers=student,
    )
    assert saved.status_code in (200, 201), saved.text
    assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student).status_code == 200
    return attempt_id


def release(client, lecturer, assessment_id):
    return client.post(f"/assessment/assessments/{assessment_id}/release-results", headers=lecturer)


def result(client, h, attempt_id):
    return client.get(f"/assessment/attempts/{attempt_id}/result", headers=h)


def assert_withheld(response):
    assert response.status_code == 409
    assert "RESULT_NOT_RELEASED" in response.text
    for leak in ("total_score", "percentage", "passed", "is_correct", "awarded_marks", "breakdown"):
        assert leak not in response.text


def assert_score_only(response):
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["max_score"] == 1
    [item] = data["breakdown"]
    assert item["is_correct"] is None
    assert item["awarded_marks"] is None
    assert item["max_marks"] == 1


def assert_feedback(response):
    assert response.status_code == 200, response.text
    [item] = response.json()["data"]["breakdown"]
    assert item["is_correct"] is True
    assert item["awarded_marks"] == 1


@pytest.mark.parametrize("visibility,timing", list(product(VISIBILITIES, TIMINGS)))
async def test_feedback_stays_null_until_its_stage(client, visibility, timing):
    lecturer, student, assessment_id = await published(client, policy(visibility, timing))
    first = take(client, student, assessment_id)

    # Before release, with attempts remaining.
    before = result(client, student, first)
    if visibility == "after_release":
        assert_withheld(before)
    elif timing == "immediate":
        assert_feedback(before)
    else:
        assert_score_only(before)

    # After release, still with attempts remaining.
    assert release(client, lecturer, assessment_id).status_code == 200
    after = result(client, student, first)
    if timing in ("immediate", "after_release"):
        assert_feedback(after)
    else:
        assert_score_only(after)

    # After the final attempt.
    take(client, student, assessment_id)
    final = result(client, student, first)
    if timing == "never":
        assert_score_only(final)
    else:
        assert_feedback(final)


async def test_after_final_attempt_waits_for_every_attempt_to_finish(client):
    _, student, assessment_id = await published(client, policy("immediate", "after_final_attempt"))
    first = take(client, student, assessment_id)
    second = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student).json()["data"]["id"]

    # Both attempts used, one still in progress.
    assert_score_only(result(client, student, first))

    assert client.post(f"/assessment/attempts/{second}/submit", headers=student).status_code == 200
    assert_feedback(result(client, student, first))


async def test_the_final_attempt_does_not_override_an_unreleased_result(client):
    lecturer, student, assessment_id = await published(client, policy("after_release", "after_final_attempt"))
    first = take(client, student, assessment_id)
    take(client, student, assessment_id)
    assert_withheld(result(client, student, first))
    assert release(client, lecturer, assessment_id).status_code == 200
    assert_feedback(result(client, student, first))


async def test_a_score_can_reveal_withheld_feedback_on_one_question(client):
    # A recorded limit, asserted on purpose: feedback timing limits what is
    # shown, and isn't a guarantee of concealment. Nobody should read it as one.
    _, student, assessment_id = await published(client, policy("immediate", "never"))
    right = take(client, student, assessment_id, right=True)
    wrong = take(client, student, assessment_id, right=False)

    for attempt_id, score in ((right, 1), (wrong, 0)):
        response = result(client, student, attempt_id)
        assert_score_only(response)
        assert response.json()["data"]["total_score"] == score


async def test_the_correct_answer_is_never_returned_at_any_stage(client):
    lecturer, student, assessment_id = await published(client, policy())
    attempt_id = take(client, student, assessment_id)
    release(client, lecturer, assessment_id)
    body = result(client, student, attempt_id).text
    for leak in ("correct_option", "explanation", "Right", "Wrong"):
        assert leak not in body


async def test_an_unsubmitted_attempt_has_no_result(client):
    _, student, assessment_id = await published(client, policy())
    attempt_id = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student).json()["data"]["id"]
    response = result(client, student, attempt_id)
    assert response.status_code == 409
    assert "total_score" not in response.text


async def test_staff_keep_their_view_before_any_release(client):
    lecturer, student, assessment_id = await published(client, policy("after_release", "never"))
    attempt_id = take(client, student, assessment_id)
    assert_withheld(result(client, student, attempt_id))
    assert_feedback(result(client, lecturer, attempt_id))


async def test_another_student_still_cannot_read_a_released_result(client):
    lecturer, student, assessment_id = await published(client, policy())
    attempt_id = take(client, student, assessment_id)
    release(client, lecturer, assessment_id)

    tenant_slug = student["X-Tenant-Slug"]
    other_id, token = await register_and_authenticate(client, f"rel-other-{uuid4()}@example.com")
    tenant_id = client.get(f"/assessment/assessments/{assessment_id}", headers=lecturer).json()["data"]["tenant_id"]
    await add_membership(other_id, tenant_id, "student")
    assert result(client, headers(token, tenant_slug), attempt_id).status_code == 404


async def test_a_repeated_release_returns_the_first_one(client):
    lecturer, _, assessment_id = await published(client, policy("after_release"))
    first = release(client, lecturer, assessment_id)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["assessment_id"] == assessment_id
    assert data["released_by"]
    assert release(client, lecturer, assessment_id).json()["data"] == data


async def test_a_student_cannot_release(client):
    _, student, assessment_id = await published(client, policy("after_release"))
    assert release(client, student, assessment_id).status_code == 403


async def test_a_draft_cannot_be_released_and_another_tenant_cannot_see_it(client):
    lecturer, _, _, draft_id = await lecturer_and_draft(client, policy("after_release"))
    assert release(client, lecturer, draft_id).status_code == 409

    other, _, _, _ = await lecturer_and_draft(client)
    assert release(client, other, draft_id).status_code == 404


@pytest.mark.parametrize(
    "scoring,stands",
    [("best", [False, True, False]), ("latest", [False, False, True]), ("first", [True, False, False])],
)
async def test_staff_see_which_attempt_stands(client, scoring, stands):
    lecturer, student, assessment_id = await published(client, policy(max_attempts=3, scoring=scoring))
    attempts = [take(client, student, assessment_id, right=right) for right in (False, True, False)]

    rows = client.get(f"/assessment/assessments/{assessment_id}/results", headers=lecturer).json()["data"]["results"]

    by_attempt = {row["attempt_id"]: row["stands"] for row in rows}
    assert [by_attempt[a] for a in attempts] == stands
