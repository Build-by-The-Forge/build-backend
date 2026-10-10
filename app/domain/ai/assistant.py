"""The AI operations the backend proxies to AI-service (design B.5, E.3).

The backend authenticates the user, resolves the tenant and membership,
checks the permission and then asks AI-service on that user's behalf. The
actor below is everything AI-service learns about the caller; it travels only
in the signed context, never in a request body.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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


QUESTION_TYPES = frozenset({"mcq", "true_false"})
DIFFICULTIES = frozenset({"easy", "medium", "hard"})
MAX_GENERATED_TEXT = 4000


@dataclass(frozen=True, slots=True)
class GeneratedOption:
    text: str
    is_correct: bool


@dataclass(frozen=True, slots=True)
class GeneratedQuestion:
    """A question proposed by AI-service in the shape of CreateQuestionRequest
    (M5 design §3). Never saved here: the lecturer reviews it and creates it
    through the assessment API."""

    question_type: str
    prompt: str
    options: tuple[GeneratedOption, ...]
    explanation: str | None
    difficulty: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_type": self.question_type,
            "prompt": self.prompt,
            "options": [{"text": o.text, "is_correct": o.is_correct} for o in self.options],
            "explanation": self.explanation,
            "difficulty": self.difficulty,
        }


def _text(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_GENERATED_TEXT:
        raise ValueError("text must be a non-empty string")
    return value


def parse_generated_question(item: object) -> GeneratedQuestion | None:
    """The backend's own check of one AI item: the backend question rules
    (known type and difficulty, at least two distinct options, exactly one
    correct; true_false is exactly True/False). None when the item fails."""
    try:
        if not isinstance(item, dict):
            raise ValueError("not an object")
        question_type, difficulty = item.get("question_type"), item.get("difficulty")
        if question_type not in QUESTION_TYPES or difficulty not in DIFFICULTIES:
            raise ValueError("unknown type or difficulty")
        raw_options = item.get("options")
        if not isinstance(raw_options, list):
            raise ValueError("options must be a list")
        options = []
        for raw in raw_options:
            if not isinstance(raw, dict) or not isinstance(raw.get("is_correct"), bool):
                raise ValueError("bad option")
            options.append(GeneratedOption(text=_text(raw.get("text")) or "", is_correct=raw["is_correct"]))
        if len(options) < 2 or sum(o.is_correct for o in options) != 1:
            raise ValueError("needs two or more options and exactly one correct")
        if len({o.text.strip().lower() for o in options}) != len(options):
            raise ValueError("options must be distinct")
        if question_type == "true_false" and sorted(o.text for o in options) != ["False", "True"]:
            raise ValueError("true_false options are True and False")
        return GeneratedQuestion(
            question_type=str(question_type),
            prompt=_text(item.get("prompt")) or "",
            options=tuple(options),
            explanation=_text(item.get("explanation"), optional=True),
            difficulty=str(difficulty),
        )
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class GeneratedQuestions:
    questions: list[GeneratedQuestion]
    discarded: int


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
    async def generate_questions(
        self, actor: AIActor, topic: str, count: int, difficulty: str, question_type: str
    ) -> GeneratedQuestions: ...
