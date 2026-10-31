"""LearningMemoryReporter: best effort, exact permission, bounded calls (M5 R3)."""

import pytest

from app.application.ai.memory_reporting import MAX_OBSERVATIONS, LearningMemoryReporter
from app.core.config import settings
from app.core.tenant_context import TenantContext
from app.domain.ai.assistant import AIAssistantError, MemoryObservation

CONTEXT = TenantContext(user_id="u-1", tenant_id="t-1", membership_id="m-1", role="student")


class Outcomes:
    def __init__(self, observations=None, error=None):
        self.observations = observations or []
        self.error = error
        self.asked = []

    async def outcomes(self, tenant_id, attempt_id, user_id):
        self.asked.append((tenant_id, attempt_id, user_id))
        if self.error:
            raise self.error
        return self.observations


class Gateway:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def record_memory(self, actor, observations):
        self.calls.append((actor, list(observations)))
        if self.error:
            raise self.error
        return []


async def report(outcomes, gateway):
    reporter = LearningMemoryReporter(outcomes)
    return await reporter.report_submitted_attempt(gateway, CONTEXT, "a-1", "corr-1")


async def test_a_closed_gate_reads_no_outcomes_and_sends_nothing(monkeypatch):
    monkeypatch.setattr(settings, "learning_memory_enabled", False)
    outcomes, gateway = Outcomes([MemoryObservation("Queues", True)]), Gateway()

    assert await report(outcomes, gateway) == 0
    assert outcomes.asked == []
    assert gateway.calls == []


async def test_reports_the_attempts_outcomes_as_the_submitting_member():
    observations = [MemoryObservation("Queues", True), MemoryObservation("Stacks", False)]
    outcomes, gateway = Outcomes(observations), Gateway()

    assert await report(outcomes, gateway) == 2

    assert outcomes.asked == [("t-1", "a-1", "u-1")]
    [(actor, sent)] = gateway.calls
    assert sent == observations
    assert (actor.tenant_id, actor.user_id, actor.membership_id, actor.role) == ("t-1", "u-1", "m-1", "student")
    assert actor.permission == "assessment.attempt.submit"
    assert actor.correlation_id == "corr-1"


async def test_nothing_to_report_makes_no_call():
    gateway = Gateway()
    assert await report(Outcomes([]), gateway) == 0
    assert gateway.calls == []


async def test_large_attempts_are_sent_in_bounded_batches():
    observations = [MemoryObservation(f"t{i}", True) for i in range(MAX_OBSERVATIONS + 5)]
    gateway = Gateway()
    assert await report(Outcomes(observations), gateway) == MAX_OBSERVATIONS + 5
    assert [len(sent) for _, sent in gateway.calls] == [MAX_OBSERVATIONS, 5]


@pytest.mark.parametrize(
    "outcomes,gateway",
    [
        (
            Outcomes([MemoryObservation("t", True)]),
            Gateway(AIAssistantError("down", error_code="X", unavailable=True)),
        ),
        (Outcomes([MemoryObservation("t", True)]), Gateway(RuntimeError("bug"))),
        (Outcomes(error=RuntimeError("db down")), Gateway()),
    ],
    ids=["ai-unavailable", "unexpected-error", "outcomes-unreadable"],
)
async def test_failures_are_logged_never_raised(outcomes, gateway):
    assert await report(outcomes, gateway) == 0
