from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.assessment.schemas import (
    AttemptQuestionOptionResponse,
    AttemptQuestionResponse,
    AttemptQuestionsResponse,
    AttemptResponse,
)
from app.application.assessment.attempt_commands import AttemptQuestionSnapshot
from app.application.assessment.attempt_service import AttemptService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.assessment.attempt import AssessmentAttempt
from app.domain.assessment.errors import AttemptAlreadySubmittedError

router = APIRouter(prefix="/assessment", tags=["assessment"])
service = build_container().get(AttemptService)


@router.post(
    "/assessments/{assessment_id}/attempts",
    status_code=status.HTTP_201_CREATED,
)
async def start_attempt(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_START)
    ),
) -> JSONResponse:
    try:
        attempt = await service.start_attempt(
            assessment_id, context.tenant_id, context.user_id
        )
    except ValueError as exc:
        if str(exc) == "assessment not found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _response(request, attempt, status_code=status.HTTP_201_CREATED)


@router.get("/attempts/{attempt_id}", status_code=status.HTTP_200_OK)
async def get_attempt(
    attempt_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_READ)
    ),
) -> JSONResponse:
    attempt = await service.get_attempt(attempt_id, context.tenant_id, context.user_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    return _response(request, attempt)


@router.get("/attempts/{attempt_id}/questions", status_code=status.HTTP_200_OK)
async def get_attempt_questions(
    attempt_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_READ)
    ),
) -> JSONResponse:
    attempt = await service.get_attempt(attempt_id, context.tenant_id, context.user_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt questions not found")
    questions = await service.get_attempt_questions(
        attempt_id, context.tenant_id, context.user_id
    )
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
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_READ)
    ),
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
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_SUBMIT)
    ),
) -> JSONResponse:
    try:
        attempt = await service.submit_attempt(
            attempt_id, context.tenant_id, context.user_id
        )
    except AttemptAlreadySubmittedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    return _response(request, attempt)


def _attempt_payload(attempt: AssessmentAttempt) -> dict[str, object]:
    return AttemptResponse(
        id=attempt.id,
        tenant_id=attempt.tenant_id,
        assessment_id=attempt.assessment_id,
        user_id=attempt.user_id,
        status=attempt.status.value,
        started_at=attempt.started_at.isoformat(),
        submitted_at=(
            attempt.submitted_at.isoformat()
            if attempt.submitted_at is not None
            else None
        ),
        created_at=attempt.created_at.isoformat(),
        updated_at=attempt.updated_at.isoformat(),
    ).model_dump()


def _question_payload(question: AttemptQuestionSnapshot) -> AttemptQuestionResponse:
    return AttemptQuestionResponse(
        question_id=question.question_id,
        sequence=question.sequence,
        prompt=question.prompt,
        marks=question.marks,
        options=[
            AttemptQuestionOptionResponse(position=index, text=text)
            for index, text in enumerate(question.options)
        ],
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
