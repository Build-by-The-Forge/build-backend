"""Report a submitted attempt's outcomes to AI-service's learning memory.

M5 ruling R3: the backend owns the facts (graded answers) and AI-service owns
the memory. Reporting is best effort and runs after the submission has been
committed: a failure is logged and never undoes or fails the submission,
since memory is derived data the backend can send again.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.core.authorization import Permission
from app.core.config import settings
from app.core.metrics import learning_memory_refusals_total
from app.core.tenant_context import TenantContext
from app.domain.ai.assistant import AIActor, AIAssistantError, AIAssistantGateway, MemoryObservation

logger = logging.getLogger(__name__)

MAX_OBSERVATIONS = 200  # AI-service's per-call bound


class AttemptTopicOutcomes(Protocol):
    async def outcomes(self, tenant_id: str, attempt_id: str, user_id: str) -> list[MemoryObservation]: ...


class LearningMemoryReporter:
    def __init__(self, outcomes: AttemptTopicOutcomes) -> None:
        self._outcomes = outcomes

    async def report_submitted_attempt(
        self,
        gateway: AIAssistantGateway,
        context: TenantContext,
        attempt_id: str,
        correlation_id: str,
    ) -> int:
        """Send the attempt's observations; returns how many were reported."""
        # Before reading the outcomes: with the gate closed, nothing is prepared
        # or sent, and the committed submission is unaffected.
        if not settings.learning_memory_allowed:
            learning_memory_refusals_total.labels(operation="write").inc()
            return 0
        try:
            observations = await self._outcomes.outcomes(context.tenant_id, attempt_id, context.user_id)
            if not observations:
                return 0
            actor = AIActor(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                membership_id=context.membership_id,
                role=context.role,
                # The permission checked for the operation that produced the
                # facts: submitting the attempt (E.6).
                permission=Permission.ASSESSMENT_ATTEMPT_SUBMIT.value,
                correlation_id=correlation_id,
            )
            for start in range(0, len(observations), MAX_OBSERVATIONS):
                await gateway.record_memory(actor, observations[start : start + MAX_OBSERVATIONS])
            return len(observations)
        except AIAssistantError as exc:
            logger.warning("learning memory not updated for attempt %s: %s (%s)", attempt_id, exc, exc.error_code)
        except Exception:
            logger.exception("learning memory not updated for attempt %s", attempt_id)
        return 0
