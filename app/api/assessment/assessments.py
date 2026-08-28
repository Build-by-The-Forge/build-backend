from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.assessment.schemas import (
    AddAssessmentQuestionRequest,
    AssessmentQuestionResponse,
    AssessmentResponse,
    CreateAssessmentRequest,
    UpdateAssessmentRequest,
)
from app.application.assessment.assessment_service import AssessmentService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.assessment.assessment import Assessment

router = APIRouter(prefix="/assessment/assessments", tags=["assessment"])
service = build_container().get(AssessmentService)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_assessment(
    request: Request,
    payload: CreateAssessmentRequest,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_CREATE)),
) -> JSONResponse:
    assessment = await service.create_assessment(
        tenant_id=context.tenant_id or "",
        course_id=payload.course_id,
        title=payload.title,
        instructions=payload.instructions,
        duration_minutes=payload.duration_minutes,
        passing_score=payload.passing_score,
    )
    return _response(
        request,
        assessment,
        status_code=status.HTTP_201_CREATED,
    )


@router.get("", status_code=status.HTTP_200_OK)
async def list_assessments(
    request: Request,
    course_id: str | None = None,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> JSONResponse:
    assessments = await service.list_assessments(
        tenant_id=context.tenant_id or "", course_id=course_id
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_assessment_payload(item) for item in assessments],
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{assessment_id}", status_code=status.HTTP_200_OK)
async def get_assessment(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> JSONResponse:
    assessment = await service.get_assessment(
        assessment_id, tenant_id=context.tenant_id or ""
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return _response(request, assessment)


@router.patch("/{assessment_id}", status_code=status.HTTP_200_OK)
async def update_assessment(
    assessment_id: str,
    request: Request,
    payload: UpdateAssessmentRequest,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_UPDATE)),
) -> JSONResponse:
    assessment = await service.update_assessment(
        assessment_id,
        context.tenant_id or "",
        title=payload.title,
        instructions=payload.instructions,
        duration_minutes=payload.duration_minutes,
        passing_score=payload.passing_score,
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return _response(request, assessment)


@router.post("/{assessment_id}/publish", status_code=status.HTTP_200_OK)
async def publish_assessment(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_PUBLISH)),
) -> JSONResponse:
    assessment = await service.publish_assessment(
        assessment_id, context.tenant_id or ""
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return _response(request, assessment)


@router.post("/{assessment_id}/questions", status_code=status.HTTP_200_OK)
async def add_question(
    assessment_id: str,
    request: Request,
    payload: AddAssessmentQuestionRequest,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_UPDATE)),
) -> JSONResponse:
    assessment = await service.add_question(
        assessment_id,
        payload.question_id,
        context.tenant_id or "",
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return _response(request, assessment)


def _assessment_payload(assessment: Assessment) -> dict[str, object]:
    return AssessmentResponse(
        id=assessment.id,
        tenant_id=assessment.tenant_id,
        course_id=assessment.course_id,
        title=assessment.title,
        instructions=assessment.instructions,
        duration_minutes=assessment.duration_minutes,
        passing_score=assessment.passing_score,
        status=assessment.status.value,
        question_count=assessment.question_count,
        questions=[
            AssessmentQuestionResponse(
                assessment_question_id=item.assessment_question_id or item.question_id,
                question_id=item.question_id,
                prompt=item.prompt,
                options=item.options,
                marks=item.marks,
            )
            for item in assessment.questions
        ],
        created_at=assessment.created_at.isoformat(),
        updated_at=assessment.updated_at.isoformat(),
    ).model_dump()


def _response(
    request: Request,
    assessment: Assessment,
    *,
    status_code: int = status.HTTP_200_OK,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": _assessment_payload(assessment),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )
