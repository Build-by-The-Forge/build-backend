from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.assessment.schemas import (
    CreateQuestionRequest,
    QuestionOptionResponse,
    QuestionResponse,
    UpdateQuestionRequest,
)
from app.application.assessment.question_service import QuestionService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext

router = APIRouter(prefix="/assessment", tags=["assessment"])
container = build_container()
service = container.get(QuestionService)


@router.post("/questions", status_code=status.HTTP_201_CREATED)
async def create_question(
    request: Request,
    payload: CreateQuestionRequest,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_QUESTION_CREATE)),
) -> JSONResponse:
    try:
        question = await service.create_question(
            topic_id=payload.topic_id,
            question_type=payload.question_type,
            prompt=payload.prompt,
            difficulty=payload.difficulty,
            marks=payload.marks,
            explanation=payload.explanation,
            learning_outcome_id=payload.learning_outcome_id,
            options=[option.model_dump() for option in payload.options],
            tenant_id=context.tenant_id,
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": QuestionResponse(
                id=question.id.value,
                topic_id=question.topic_id,
                learning_outcome_id=question.learning_outcome_id,
                question_type=question.question_type.value,
                prompt=question.prompt.value,
                explanation=(question.explanation.value if question.explanation else None),
                difficulty=question.difficulty.value,
                marks=question.marks.value,
                status=question.status.value,
                options=[
                    QuestionOptionResponse(
                        id=option.id.value,
                        text=option.text.value,
                        display_order=option.display_order.value,
                        is_correct=option.is_correct,
                    )
                    for option in question.options
                ],
            ).model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/questions/{question_id}", status_code=status.HTTP_200_OK)
async def get_question(
    question_id: str,
    request: Request,
    # The answer key and explanation: authors only, never assessment.read.
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_QUESTION_UPDATE)),
) -> JSONResponse:
    question = await service.get_question(question_id, tenant_id=context.tenant_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": QuestionResponse(
                id=question.id.value,
                topic_id=question.topic_id,
                learning_outcome_id=question.learning_outcome_id,
                question_type=question.question_type.value,
                prompt=question.prompt.value,
                explanation=(question.explanation.value if question.explanation else None),
                difficulty=question.difficulty.value,
                marks=question.marks.value,
                status=question.status.value,
                options=[
                    QuestionOptionResponse(
                        id=option.id.value,
                        text=option.text.value,
                        display_order=option.display_order.value,
                        is_correct=option.is_correct,
                    )
                    for option in question.options
                ],
            ).model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.patch("/questions/{question_id}", status_code=status.HTTP_200_OK)
async def update_question(
    question_id: str,
    request: Request,
    payload: UpdateQuestionRequest,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_QUESTION_UPDATE)),
) -> JSONResponse:
    question = await service.update_question(
        question_id=question_id,
        tenant_id=context.tenant_id,
        prompt=payload.prompt,
        explanation=payload.explanation,
        difficulty=payload.difficulty,
        marks=payload.marks,
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": QuestionResponse(
                id=question.id.value,
                topic_id=question.topic_id,
                learning_outcome_id=question.learning_outcome_id,
                question_type=question.question_type.value,
                prompt=question.prompt.value,
                explanation=(question.explanation.value if question.explanation else None),
                difficulty=question.difficulty.value,
                marks=question.marks.value,
                status=question.status.value,
                options=[
                    QuestionOptionResponse(
                        id=option.id.value,
                        text=option.text.value,
                        display_order=option.display_order.value,
                        is_correct=option.is_correct,
                    )
                    for option in question.options
                ],
            ).model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/questions/{question_id}/publish", status_code=status.HTTP_200_OK)
async def publish_question(
    question_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_QUESTION_PUBLISH)),
) -> JSONResponse:
    question = await service.publish_question(question_id, tenant_id=context.tenant_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"id": question.id.value, "status": question.status.value},
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/questions/{question_id}/archive", status_code=status.HTTP_200_OK)
async def archive_question(
    question_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_QUESTION_ARCHIVE)),
) -> JSONResponse:
    question = await service.archive_question(question_id, tenant_id=context.tenant_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"id": question.id.value, "status": question.status.value},
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )
