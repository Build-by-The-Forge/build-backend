from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.ai import correlation_id_for, get_ai_assistant_gateway
from app.api.assessment.schemas import (
    AttemptQuestionOptionResponse,
    AttemptQuestionResponse,
    AttemptQuestionsResponse,
    AttemptResponse,
    AttemptResultResponse,
    QuestionResultResponse,
)
from app.application.ai.memory_reporting import LearningMemoryReporter
from app.application.assessment.attempt_commands import AttemptQuestionSnapshot
from app.application.assessment.attempt_service import AttemptService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.ai.assistant import AIAssistantGateway
from app.domain.assessment.attempt import AssessmentAttempt
from app.domain.assessment.errors import AttemptLimitReachedError, ResultNotReleasedError
from app.infrastructure.assessment.attempt_topic_outcomes import SqlAlchemyAttemptTopicOutcomes

router = APIRouter(prefix="/assessment", tags=["assessment"])
service = build_container().get(AttemptService)
memory_reporter = LearningMemoryReporter(SqlAlchemyAttemptTopicOutcomes())


@router.post(
    "/assessments/{assessment_id}/attempts",
    status_code=status.HTTP_201_CREATED,
)
async def start_attempt(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_ATTEMPT_START)),
) -> JSONResponse:
    try:
        attempt = await service.start_attempt(assessment_id, context.tenant_id, context.user_id)
    except AttemptLimitReachedError as exc:
        raise HTTPException(status_code=409, detail="ATTEMPT_LIMIT_REACHED") from exc
    except ValueError as exc:
        if str(exc) == "assessment not found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _response(request, attempt, status_code=status.HTTP_201_CREATED)


@router.get("/attempts/{attempt_id}", status_code=status.HTTP_200_OK)
async def get_attempt(
    attempt_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_ATTEMPT_READ)),
) -> JSONResponse:
    attempt = await service.get_attempt(attempt_id, context.tenant_id, context.user_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    return _response(request, attempt)


@router.get("/attempts/{attempt_id}/questions", status_code=status.HTTP_200_OK)
async def get_attempt_questions(
    attempt_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_ATTEMPT_READ)),
) -> JSONResponse:
    attempt = await service.get_attempt(attempt_id, context.tenant_id, context.user_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt questions not found")
    questions = await service.get_attempt_questions(attempt_id, context.tenant_id, context.user_id)
    if questions is None:
        raise HTTPException(status_code=404, detail="attempt questions not found")

    response = AttemptQuestionsResponse(
        attempt_id=attempt_id,
        assessment_id=attempt.assessment_id,
        questions=[_question_payload(question) for question in questions],
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": response.model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/attempts", status_code=status.HTTP_200_OK)
async def list_attempts(
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_ATTEMPT_READ)),
) -> JSONResponse:
    attempts = await service.list_my_attempts(context.tenant_id, context.user_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_attempt_payload(attempt) for attempt in attempts],
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/attempts/{attempt_id}/submit", status_code=status.HTTP_200_OK)
async def submit_attempt(
    attempt_id: str,
    request: Request,
    background: BackgroundTasks,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_ATTEMPT_SUBMIT)),
    gateway: AIAssistantGateway = Depends(get_ai_assistant_gateway),
) -> JSONResponse:
    attempt = await service.submit_attempt(attempt_id, context.tenant_id, context.user_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    # After the response, and only once the graded attempt is committed: the
    # learner's memory in AI-service (M5 ruling R3). Best effort.
    if attempt.newly_submitted:
        background.add_task(
            memory_reporter.report_submitted_attempt,
            gateway,
            context,
            attempt_id,
            correlation_id_for(request),
        )
    return _response(request, attempt)


@router.get("/attempts/{attempt_id}/result", status_code=status.HTTP_200_OK)
async def get_attempt_result(
    attempt_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_ATTEMPT_RESULT_READ)),
) -> JSONResponse:
    is_staff = context.role in {"lecturer", "hod", "faculty_admin", "admin", "owner"}
    try:
        readable = await service.get_attempt_result(
            attempt_id=attempt_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            is_staff=is_staff,
        )
    except ResultNotReleasedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RESULT_NOT_RELEASED") from exc
    except ValueError as exc:
        if str(exc) == "attempt is not submitted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="attempt is not submitted",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if readable is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="attempt result not found",
        )

    result, shown = readable.result, readable.feedback_shown
    response = AttemptResultResponse(
        id=result.id,
        tenant_id=result.tenant_id,
        attempt_id=result.attempt_id,
        assessment_id=result.assessment_id,
        user_id=result.user_id,
        total_score=result.total_score,
        max_score=result.max_score,
        percentage=result.percentage,
        passed=result.passed,
        graded_at=result.graded_at.isoformat(),
        breakdown=[
            QuestionResultResponse(
                assessment_question_id=item.assessment_question_id,
                selected_option_index=item.selected_option_index,
                awarded_marks=item.awarded_marks if shown else None,
                max_marks=item.max_marks,
                is_correct=item.is_correct if shown else None,
            )
            for item in result.breakdown
        ],
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": response.model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _attempt_payload(attempt: AssessmentAttempt) -> dict[str, object]:
    return AttemptResponse(
        id=attempt.id,
        tenant_id=attempt.tenant_id,
        assessment_id=attempt.assessment_id,
        user_id=attempt.user_id,
        status=attempt.status.value,
        started_at=attempt.started_at.isoformat(),
        expires_at=attempt.expires_at.isoformat(),
        submitted_at=(attempt.submitted_at.isoformat() if attempt.submitted_at is not None else None),
        created_at=attempt.created_at.isoformat(),
        updated_at=attempt.updated_at.isoformat(),
    ).model_dump()


def _question_payload(question: AttemptQuestionSnapshot) -> AttemptQuestionResponse:
    return AttemptQuestionResponse(
        assessment_question_id=question.assessment_question_id,
        question_id=question.question_id,
        sequence=question.sequence,
        prompt=question.prompt,
        marks=question.marks,
        options=[AttemptQuestionOptionResponse(position=index, text=text) for index, text in enumerate(question.options)],
    )


def _response(
    request: Request,
    attempt: AssessmentAttempt,
    *,
    status_code: int = status.HTTP_200_OK,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": _attempt_payload(attempt),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )
