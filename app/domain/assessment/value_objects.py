from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class QuestionId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class QuestionOptionId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class QuestionPrompt:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if not v:
            raise ValueError("non-empty prompt required")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class QuestionExplanation:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if not v:
            raise ValueError("question explanation must be a non-empty string")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class QuestionMarks:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("question marks must be positive")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class QuestionDisplayOrder:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("question display order must be positive")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class QuestionOptionText:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if not v:
            raise ValueError("non-empty option text required")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


class QuestionType(str, Enum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
