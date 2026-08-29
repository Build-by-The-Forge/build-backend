from dataclasses import dataclass


@dataclass(slots=True)
class SaveAttemptAnswerCommand:
    attempt_id: str
    assessment_question_id: str
    selected_option_index: int
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class GetAttemptAnswersCommand:
    attempt_id: str
    tenant_id: str
    user_id: str


@dataclass(slots=True)
class DeleteAttemptAnswerCommand:
    attempt_id: str
    assessment_question_id: str
    tenant_id: str
    user_id: str
