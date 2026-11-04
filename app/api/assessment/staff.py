"""Staff reads of assessments (M3-E), outside the mobile contract.

The mobile routes show only published assessments in visible courses, and no
questions, to everyone. Authoring needs the rest: drafts, assessments of
hidden courses, and the questions with their options. Those come only from
here, and only with ``assessment.update`` in the caller's tenant.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.assessment.assessments import _assessment_payload, _response, service
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.exceptions import ClientHTTPException
from app.core.tenant_context import TenantContext

router = APIRouter(prefix="/assessment/staff/assessments", tags=["assessment-staff"])

StatusFilter = Literal["draft", "published", "open", "closed", "archived"]


@router.get("", status_code=status.HTTP_200_OK)
async def list_staff_assessments(
    request: Request,
    course_id: str | None = None,
    status_filter: StatusFilter | None = Query(default=None, alias="status"),
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_UPDATE)),
) -> JSONResponse:
    assessments = await service.list_assessments(tenant_id=context.tenant_id or "", course_id=course_id)
    if status_filter is not None:
        assessments = [item for item in assessments if item.status.value == status_filter]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_assessment_payload(item, with_questions=True) for item in assessments],
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.get("/{assessment_id}", status_code=status.HTTP_200_OK)
async def get_staff_assessment(
    assessment_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.ASSESSMENT_UPDATE)),
) -> JSONResponse:
    assessment = await service.get_assessment(assessment_id, tenant_id=context.tenant_id or "")
    if assessment is None:
        raise ClientHTTPException(status_code=404, detail="assessment not found")
    return _response(request, assessment, with_questions=True)
