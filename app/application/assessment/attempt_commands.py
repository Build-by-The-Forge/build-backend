from dataclasses import dataclass


@dataclass(slots=True)
class AttemptQuestionSnapshot:
    assessment_question_id: str
    question_id: str
    sequence: int
    prompt: str
    options: list[str]
    marks: int


@dataclass(slots=True)
class StartAttemptCommand:
    assessment_id: str
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class GetAttemptCommand:
    attempt_id: str
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class ListMyAttemptsCommand:
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class SubmitAttemptCommand:
    attempt_id: str
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class GetAttemptQuestionsCommand:
    attempt_id: str
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class GetAttemptResultCommand:
    attempt_id: str
    tenant_id: str
    user_id: str
    is_staff: bool = False
