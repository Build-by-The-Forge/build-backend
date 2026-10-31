"""With the learning-memory gate closed, the backend sends nothing and
assessment submission is unaffected. The real gateway over a counting transport:
a closed gate must mean no request leaves this service."""

import logging

import httpx
import pytest
from prometheus_client import generate_latest

from app import main
from app.api.ai import get_ai_assistant_gateway
from app.core.config import settings
from app.core.metrics import registry
from app.infrastructure.ai.assistant_gateway import HttpAIAssistantGateway
from app.infrastructure.security.service_signature import ServiceKeys
from app.main import app
from tests.integration.ai.test_memory_reporting_api import answer, published_assessment, student_attempt


@pytest.fixture
def closed(monkeypatch):
    monkeypatch.setattr(settings, "learning_memory_enabled", False)


@pytest.fixture
def sent():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True, "data": {"items": []}, "message": ""})

    gateway = HttpAIAssistantGateway(
        base_url="http://ai-service.internal",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        keys=ServiceKeys(current="test-backend-to-ai-secret-for-assistant-tests-01"),
    )
    app.dependency_overrides[get_ai_assistant_gateway] = lambda: gateway
    yield requests
    app.dependency_overrides.pop(get_ai_assistant_gateway, None)


def refusals(operation: str) -> float:
    line = f'build_backend_learning_memory_refusals_total{{operation="{operation}"}} '
    for row in generate_latest(registry).decode().splitlines():
        if row.startswith(line):
            return float(row.removeprefix(line))
    return 0.0


async def test_a_submission_is_graded_and_nothing_is_sent(client, closed, sent, caplog):
    tenant_id, slug, assessment_id = await published_assessment(client, 2)
    _, h, attempt_id, questions = await student_attempt(client, tenant_id, slug, assessment_id)
    answer(client, h, attempt_id, questions[0], 1)
    answer(client, h, attempt_id, questions[1], 0)
    before = refusals("write")

    with caplog.at_level(logging.DEBUG):
        submitted = client.post(f"/assessment/attempts/{attempt_id}/submit", headers=h)

    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "submitted"
    assert sent == []
    assert refusals("write") == before + 1
    assert "Assessment Topic" not in caplog.text

    # The authoritative result exists, and repeating the submit stays safe.
    result = client.get(f"/assessment/attempts/{attempt_id}/result", headers=h)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["total_score"] == 1
    assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=h).status_code == 200
    assert sent == []


async def test_the_same_submission_does_send_with_the_gate_open(client, sent):
    # The control: the assertions above can't pass merely because this path
    # sends nothing in tests.
    tenant_id, slug, assessment_id = await published_assessment(client, 1)
    _, h, attempt_id, questions = await student_attempt(client, tenant_id, slug, assessment_id)
    answer(client, h, attempt_id, questions[0], 1)
    assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=h).status_code == 200
    assert [r.url.path for r in sent] == ["/v1/ai/memory/upsert"]


async def test_reading_memory_answers_503_and_sends_nothing(client, closed, sent):
    tenant_id, slug, assessment_id = await published_assessment(client, 1)
    _, h, _, _ = await student_attempt(client, tenant_id, slug, assessment_id)
    before = refusals("read")

    response = client.get("/ai/memory", params=[("topic", "algebra")], headers=h)

    assert response.status_code == 503
    assert "algebra" not in response.text
    assert sent == []
    assert refusals("read") == before + 1


async def test_a_closed_gate_does_not_replace_authentication_or_validation(client, closed, sent):
    assert client.get("/ai/memory").status_code == 401
    tenant_id, slug, assessment_id = await published_assessment(client, 1)
    _, h, _, _ = await student_attempt(client, tenant_id, slug, assessment_id)
    assert client.get("/ai/memory", params=[("topic", "x" * 256)], headers=h).status_code == 422
    assert sent == []


@pytest.mark.parametrize("requested,expected", [(False, 0.0), (True, 1.0)])
async def test_startup_reports_the_state_once(monkeypatch, requested, expected):
    monkeypatch.setattr(settings, "learning_memory_enabled", requested)
    lines = []
    monkeypatch.setattr(main.logger, "info", lambda message, *args: lines.append(message))

    async with main.lifespan(app):
        pass

    assert len([line for line in lines if line.startswith("Learning memory:")]) == 1
    assert f"build_backend_learning_memory_enabled {expected}" in generate_latest(registry).decode()
