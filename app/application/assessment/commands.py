from dataclasses import dataclass


@dataclass(slots=True)
class CreateQuestionCommand:
    topic_id: str
    question_type: str
    prompt: str
    difficulty: str = "medium"
    marks: int = 1
    explanation: str | None = None
    learning_outcome_id: str | None = None
    options: list[dict[str, object]] | None = None
    tenant_id: str | None = None


@dataclass(slots=True)
class UpdateQuestionCommand:
    question_id: str
    prompt: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    marks: int | None = None
    tenant_id: str | None = None


@dataclass(slots=True)
class PublishQuestionCommand:
    question_id: str
    tenant_id: str | None = None


@dataclass(slots=True)
class ArchiveQuestionCommand:
    question_id: str
    tenant_id: str | None = None


@dataclass(slots=True)
class GetQuestionCommand:
    question_id: str
    tenant_id: str | None = None


@dataclass(slots=True)
class ListQuestionsByTopicCommand:
    topic_id: str
    tenant_id: str | None = None


@dataclass(slots=True)
class ListQuestionsByLearningOutcomeCommand:
    learning_outcome_id: str
    tenant_id: str | None = None
