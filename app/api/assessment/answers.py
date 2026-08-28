from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.assessment.schemas import (
    AttemptAnswerResponse,
    AttemptAnswersResponse,
    SaveAttemptAnswerRequest,
)
from app.application.assessment.attempt_answer_service import AttemptAnswerService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.assessment.errors import AttemptAlreadySubmittedError

router = APIRouter(prefix="/assessment", tags=["assessment"])
service = build_container().get(AttemptAnswerService)


@router.put(
    "/attempts/{attempt_id}/answers/{assessment_question_id}",
    status_code=status.HTTP_200_OK,
)
async def save_answer(
    attempt_id: str,
    assessment_question_id: str,
    request: Request,
    payload: SaveAttemptAnswerRequest,
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_ANSWER_WRITE)
    ),
) -> JSONResponse:
    try:
        answer = await service.save_answer(
            attempt_id,
            assessment_question_id,
            payload.selected_option_index,
            context.tenant_id,
            context.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttemptAlreadySubmittedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(request, answer)


@router.get("/attempts/{attempt_id}/answers", status_code=status.HTTP_200_OK)
async def get_answers(
    attempt_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_READ)
    ),
) -> JSONResponse:
    answers = await service.get_answers(attempt_id, context.tenant_id, context.user_id)
    if answers is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    response = AttemptAnswersResponse(
        attempt_id=attempt_id,
        answers=[
            AttemptAnswerResponse(
                attempt_id=answer.attempt_id,
                assessment_question_id=answer.assessment_question_id,
                selected_option_index=answer.selected_option_index,
                updated_at=answer.updated_at.isoformat(),
            )
            for answer in answers
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


@router.delete(
    "/attempts/{attempt_id}/answers/{assessment_question_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_answer(
    attempt_id: str,
    assessment_question_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.ASSESSMENT_ATTEMPT_ANSWER_DELETE)
    ),
) -> JSONResponse:
    try:
        deleted = await service.delete_answer(
            attempt_id,
            assessment_question_id,
            context.tenant_id,
            context.user_id,
        )
    except AttemptAlreadySubmittedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if deleted is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {},
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _response(request: Request, answer) -> JSONResponse:
    payload = AttemptAnswerResponse(
        attempt_id=answer.attempt_id,
        assessment_question_id=answer.assessment_question_id,
        selected_option_index=answer.selected_option_index,
        updated_at=answer.updated_at.isoformat(),
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": payload.model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )