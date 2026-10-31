"""A refused value stays out of the response and the logs: it may be a password."""

import logging
from uuid import uuid4

import pytest

from tests.integration.assessment.test_question_api import register_and_authenticate

SECRET = "Sup3r-Secret-Value-987654321"


def test_a_public_route_does_not_echo_a_refused_value(client):
    response = client.post("/identity/users", json={"email": "someone@example.com", "password": [SECRET]})
    assert response.status_code == 422
    assert SECRET not in response.text


def test_validation_details_name_the_problem_without_the_value(client):
    response = client.post("/identity/users", json={"email": "someone@example.com", "password": [SECRET]})
    details = response.json()["meta"]["details"]
    assert details
    for detail in details:
        assert set(detail) == {"type", "loc", "msg"}


@pytest.mark.asyncio
async def test_a_signed_in_route_does_not_log_a_refused_value(client, caplog):
    _, token = await register_and_authenticate(client, f"echo-{uuid4()}@example.com")
    caplog.set_level(logging.DEBUG)
    response = client.post(
        "/identity/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json=[SECRET],
    )
    assert response.status_code == 422
    assert SECRET not in response.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize(
    "body",
    ['{"email": "a@example.com", "password": "' + SECRET, f'["{SECRET}"]', f'"{SECRET}"', SECRET],
    ids=["truncated-json", "array", "string", "not-json"],
)
def test_malformed_bodies_are_not_echoed(client, caplog, body):
    caplog.set_level(logging.DEBUG)
    response = client.post("/identity/users", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert SECRET not in response.text
    assert SECRET not in caplog.text
