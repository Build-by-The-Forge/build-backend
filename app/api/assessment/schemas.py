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
