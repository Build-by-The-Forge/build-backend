"""The AI operations the backend proxies to AI-service (design B.5, E.3).

The backend authenticates the user, resolves the tenant and membership,
checks the permission and then asks AI-service on that user's behalf. The
actor below is everything AI-service learns about the caller; it travels only
in the signed context, never in a request body.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AIActor:
    tenant_id: str
    user_id: str
    membership_id: str
    role: str
    permission: str  # the one permission checked for this operation (E.6)
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ChatAnswer:
    answer: str
    context: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Explanation:
    explanation: str


@dataclass(frozen=True, slots=True)
class GeneratedQuestions:
    questions: str


class AIAssistantError(Exception):
    """AI-service did not produce a usable answer. ``unavailable`` marks a
    failure to reach it (503) as opposed to a bad or refused exchange (502)."""

    def __init__(self, message: str, *, error_code: str, unavailable: bool = False) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.unavailable = unavailable


class AIAssistantGateway(ABC):
    @abstractmethod
    async def chat(self, actor: AIActor, message: str) -> ChatAnswer: ...

    @abstractmethod
    async def explain(self, actor: AIActor, subject: str) -> Explanation: ...

    @abstractmethod
    async def generate_questions(self, actor: AIActor, topic: str, count: int) -> GeneratedQuestions: ...
