from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.assessment.schemas import (
    AddAssessmentQuestionRequest,
    AssessmentAttemptResultSummaryResponse,
    AssessmentQuestionResponse,
    AssessmentResponse,
    AssessmentResultsResponse,
    AttemptPolicyBody,
    CreateAssessmentRequest,
    UpdateAssessmentRequest,
)
from app.application.assessment.assessment_service import AssessmentService
from app.application.assessment.attempt_service import AttemptService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.exceptions import ClientHTTPException, public_message
from app.core.tenant_context import TenantContext
from app.domain.assessment.assessment import Assessment
from app.domain.assessment.errors import AttemptPolicyLockedError

router = APIRouter(prefix="/assessment/assessments", tags=["assessment"])
service = build_container().get(AssessmentService)
attempt_service = build_container().get(AttemptService)


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
        attempt_policy=payload.attempt_policy.to_domain() if payload.attempt_policy else None,
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
    # The same for everyone, staff included (M3-E decisions 1 to 3): published,
    # in a visible course, and never with questions. Staff read drafts, hidden
    # courses and questions on /assessment/staff/assessments.
    assessments = await service.list_readable_assessments(context.tenant_id or "", course_id)
    used = await attempt_service.attempts_used(context.tenant_id or "", context.user_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [
                _assessment_payload(item, attempts_used=used.get(item.id, 0), question_count=count) for item, count in assessments
            ],
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.get("/{assessment_id}", status_code=status.HTTP_200_OK)
async def get_assessment(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> JSONResponse:
    # A draft or hidden assessment is the same 404 as one that doesn't exist,
    # whoever asks and whatever they hold.
    readable = await service.get_readable_assessment(assessment_id, context.tenant_id or "")
    if readable is None:
        raise ClientHTTPException(status_code=404, detail="assessment not found")
    assessment, count = readable
    used = await attempt_service.attempts_used(context.tenant_id or "", context.user_id)
    return _response(request, assessment, attempts_used=used.get(assessment.id, 0), question_count=count)


@router.patch("/{assessment_id}", status_code=status.HTTP_200_OK)
async def update_assessment(
    assessment_id: str,
    request: Request,
    payload: UpdateAssessmentRequest,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_UPDATE)),
) -> JSONResponse:
    try:
        assessment = await service.update_assessment(
            assessment_id,
            context.tenant_id or "",
            title=payload.title,
            instructions=payload.instructions,
            duration_minutes=payload.duration_minutes,
            passing_score=payload.passing_score,
            attempt_policy=payload.attempt_policy.to_domain() if payload.attempt_policy else None,
        )
    except AttemptPolicyLockedError as exc:
        raise ClientHTTPException(status_code=409, detail=public_message(exc)) from exc
    if assessment is None:
        raise ClientHTTPException(status_code=404, detail="assessment not found")
    return _response(request, assessment)


@router.post("/{assessment_id}/publish", status_code=status.HTTP_200_OK)
async def publish_assessment(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_PUBLISH)),
) -> JSONResponse:
    assessment = await service.publish_assessment(assessment_id, context.tenant_id or "")
    if assessment is None:
        raise ClientHTTPException(status_code=404, detail="assessment not found")
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
        raise ClientHTTPException(status_code=404, detail="assessment not found")
    return _response(request, assessment)


@router.post("/{assessment_id}/release-results", status_code=status.HTTP_200_OK)
async def release_results(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_PUBLISH)),
) -> JSONResponse:
    try:
        release = await service.release_results(assessment_id, context.tenant_id or "", context.user_id)
    except ValueError as exc:
        raise ClientHTTPException(status_code=409, detail=public_message(exc)) from exc
    if release is None:
        raise ClientHTTPException(status_code=404, detail="assessment not found")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "assessment_id": release.assessment_id,
                "released_by": release.released_by,
                "released_at": release.released_at.isoformat(),
            },
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.get("/{assessment_id}/results", status_code=status.HTTP_200_OK)
async def get_assessment_results(
    assessment_id: str,
    request: Request,
    limit: int = 50,
    offset: int = 0,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_RESULT_READ)),
) -> JSONResponse:
    if limit < 1 or limit > 100:
        raise ClientHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100",
        )
    if offset < 0:
        raise ClientHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="offset must be greater than or equal to 0",
        )

    result_data = await service.get_assessment_results(
        assessment_id=assessment_id,
        tenant_id=context.tenant_id or "",
        limit=limit,
        offset=offset,
    )
    if result_data is None:
        raise ClientHTTPException(status_code=404, detail="assessment not found")

    results, total = result_data
    standing = await service.standing_attempts(assessment_id, context.tenant_id or "")
    response = AssessmentResultsResponse(
        assessment_id=assessment_id,
        results=[
            AssessmentAttemptResultSummaryResponse(
                attempt_id=item.attempt_id,
                user_id=item.user_id,
                total_score=item.total_score,
                max_score=item.max_score,
                percentage=item.percentage,
                passed=item.passed,
                graded_at=item.graded_at.isoformat(),
                stands=item.attempt_id in standing,
            )
            for item in results
        ],
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": response.model_dump(),
            "error": None,
            "meta": {"total": total, "limit": limit, "offset": offset, "request_id": getattr(request.state, "request_id", None)},
        },
    )


def _assessment_payload(
    assessment: Assessment, *, with_questions: bool = True, attempts_used: int = 0, question_count: int | None = None
) -> dict[str, object]:
    # A mobile read passes question_count from SQL and loads no questions;
    # without one, the questions are loaded and counted.
    if question_count is not None and assessment.questions:
        raise RuntimeError("a counted assessment must not carry its questions")
    return AssessmentResponse(
        id=assessment.id,
        tenant_id=assessment.tenant_id,
        course_id=assessment.course_id,
        title=assessment.title,
        instructions=assessment.instructions,
        duration_minutes=assessment.duration_minutes,
        passing_score=assessment.passing_score,
        status=assessment.status.value,
        question_count=assessment.question_count if question_count is None else question_count,
        attempt_policy=AttemptPolicyBody.from_domain(assessment.attempt_policy),
        attempts_used=attempts_used,
        questions=[
            AssessmentQuestionResponse(
                assessment_question_id=item.assessment_question_id or item.question_id,
                question_id=item.question_id,
                prompt=item.prompt,
                options=item.options,
                marks=item.marks,
            )
            for item in (assessment.questions if with_questions and question_count is None else [])
        ],
        created_at=assessment.created_at.isoformat(),
        updated_at=assessment.updated_at.isoformat(),
    ).model_dump()


def _response(
    request: Request,
    assessment: Assessment,
    *,
    status_code: int = status.HTTP_200_OK,
    with_questions: bool = True,
    attempts_used: int = 0,
    question_count: int | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": _assessment_payload(
                assessment, with_questions=with_questions, attempts_used=attempts_used, question_count=question_count
            ),
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )
