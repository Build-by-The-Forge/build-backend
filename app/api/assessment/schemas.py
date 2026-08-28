from pydantic import BaseModel, ConfigDict


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


class CreateAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    title: str
    instructions: str
    duration_minutes: int
    passing_score: int = 0


class UpdateAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = None
    passing_score: int | None = None


class AssessmentQuestionResponse(BaseModel):
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
