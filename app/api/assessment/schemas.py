from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.assessment.attempt_policy import (
    AttemptKind,
    AttemptPolicy,
    FeedbackTiming,
    ResultVisibility,
    ScoringPolicy,
)


class QuestionOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    display_order: int
    is_correct: bool = False


class CreateQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    learning_outcome_id: str | None = None
    question_type: str
    prompt: str
    explanation: str | None = None
    difficulty: str = "medium"
    marks: int = 1
    options: list[QuestionOptionInput]


class UpdateQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    marks: int | None = None


class QuestionOptionResponse(BaseModel):
    id: str
    text: str
    display_order: int
    is_correct: bool


class QuestionResponse(BaseModel):
    id: str
    topic_id: str
    learning_outcome_id: str | None = None
    question_type: str
    prompt: str
    explanation: str | None = None
    difficulty: str
    marks: int
    status: str
    options: list[QuestionOptionResponse]


class AttemptPolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["practice", "formal"]
    max_attempts: int | None
    retake_after_submission: bool
    result_visibility: Literal["immediate", "after_release"]
    feedback_timing: Literal["immediate", "after_final_attempt", "after_release", "never"]
    scoring_policy: Literal["best", "latest", "first"]

    @model_validator(mode="after")
    def _valid_combination(self) -> "AttemptPolicyBody":
        self.to_domain()
        return self

    def to_domain(self) -> AttemptPolicy:
        return AttemptPolicy(
            kind=AttemptKind(self.kind),
            max_attempts=self.max_attempts,
            retake_after_submission=self.retake_after_submission,
            result_visibility=ResultVisibility(self.result_visibility),
            feedback_timing=FeedbackTiming(self.feedback_timing),
            scoring_policy=ScoringPolicy(self.scoring_policy),
        )

    @classmethod
    def from_domain(cls, policy: AttemptPolicy) -> "AttemptPolicyBody":
        return cls(
            kind=policy.kind.value,
            max_attempts=policy.max_attempts,
            retake_after_submission=policy.retake_after_submission,
            result_visibility=policy.result_visibility.value,
            feedback_timing=policy.feedback_timing.value,
            scoring_policy=policy.scoring_policy.value,
        )


class CreateAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    title: str
    instructions: str
    duration_minutes: int
    passing_score: int = 0
    attempt_policy: AttemptPolicyBody | None = None


class UpdateAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = None
    passing_score: int | None = None
    attempt_policy: AttemptPolicyBody | None = None


class AssessmentQuestionResponse(BaseModel):
    assessment_question_id: str
    question_id: str
    prompt: str
    options: list[str]
    marks: int


class AssessmentResponse(BaseModel):
    id: str
    tenant_id: str
    course_id: str
    title: str
    instructions: str
    duration_minutes: int
    passing_score: int
    status: str
    question_count: int
    attempt_policy: AttemptPolicyBody
    attempts_used: int
    questions: list[AssessmentQuestionResponse]
    created_at: str
    updated_at: str


class AddAssessmentQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str


class AttemptResponse(BaseModel):
    id: str
    tenant_id: str
    assessment_id: str
    user_id: str
    status: str
    started_at: str
    expires_at: str
    submitted_at: str | None = None
    created_at: str
    updated_at: str


class AttemptQuestionOptionResponse(BaseModel):
    position: int
    text: str


class AttemptQuestionResponse(BaseModel):
    assessment_question_id: str
    question_id: str
    sequence: int
    prompt: str
    marks: int
    options: list[AttemptQuestionOptionResponse]


class AttemptQuestionsResponse(BaseModel):
    attempt_id: str
    assessment_id: str
    questions: list[AttemptQuestionResponse]


class SaveAttemptAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_option_index: int


class AttemptAnswerResponse(BaseModel):
    attempt_id: str
    assessment_question_id: str
    selected_option_index: int
    updated_at: str


class AttemptAnswersResponse(BaseModel):
    attempt_id: str
    answers: list[AttemptAnswerResponse]


class QuestionResultResponse(BaseModel):
    assessment_question_id: str
    selected_option_index: int | None
    awarded_marks: int | None
    max_marks: int
    is_correct: bool | None


class AttemptResultResponse(BaseModel):
    id: str
    tenant_id: str
    attempt_id: str
    assessment_id: str
    user_id: str
    total_score: int
    max_score: int
    percentage: float
    passed: bool
    graded_at: str
    breakdown: list[QuestionResultResponse]


class AssessmentAttemptResultSummaryResponse(BaseModel):
    attempt_id: str
    user_id: str
    total_score: int
    max_score: int
    percentage: float
    passed: bool
    graded_at: str
    stands: bool


class AssessmentResultsResponse(BaseModel):
    assessment_id: str
    results: list[AssessmentAttemptResultSummaryResponse]
