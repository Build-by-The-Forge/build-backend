"""The student's academic profile (S-02): GET and PUT /academic/profile."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, StringConstraints, field_validator

from app.application.academic.profile_service import AcademicProfileService
from app.bootstrap.container import build_container
from app.core.dependencies import get_current_tenant_context
from app.core.exceptions import ClientHTTPException
from app.core.tenant_context import TenantContext
from app.domain.academic.profile import MAX_COURSES, AcademicProfile, NotAStudentMember, UnavailableReferences
from app.domain.client_safe import ClientSafeError
from app.domain.tenant.value_objects import MembershipRole

router = APIRouter(prefix="/academic", tags=["academic"])
service = build_container().get(AcademicProfileService)

ReferenceId = Annotated[StrictStr, StringConstraints(min_length=1, max_length=36)]


class AcademicProfileUpdate(BaseModel):
    """The whole profile: all three fields, course_ids possibly empty."""

    model_config = ConfigDict(extra="forbid")

    programme_id: ReferenceId
    level: StrictInt
    course_ids: list[ReferenceId] = Field(max_length=MAX_COURSES)

    @field_validator("course_ids")
    @classmethod
    def _each_course_once(cls, course_ids: list[str]) -> list[str]:
        if len(set(course_ids)) != len(course_ids):
            raise ClientSafeError("a course can be listed only once")
        return course_ids


async def student(context: TenantContext = Depends(get_current_tenant_context)) -> TenantContext:
    """Student memberships only (decision 7). A role check, not a permission:
    owners and admins hold every permission, and the profile isn't theirs."""
    if context.role != MembershipRole.STUDENT.value:
        raise _refused()
    return context


def _envelope(request: Request, profile: AcademicProfile) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "programme": asdict(profile.programme) if profile.programme else None,
                "department": asdict(profile.department) if profile.department else None,
                "faculty": asdict(profile.faculty) if profile.faculty else None,
                "level": profile.level,
                "courses": [asdict(course) for course in profile.courses],
                "complete": profile.complete,
                "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            },
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


def _refused() -> ClientHTTPException:
    return ClientHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")


@router.get("/profile", status_code=status.HTTP_200_OK)
async def get_academic_profile(request: Request, context: TenantContext = Depends(student)) -> JSONResponse:
    try:
        return _envelope(request, await service.get(context.tenant_id, context.user_id))
    except NotAStudentMember:
        # The membership changed after the tenant guard read it.
        raise _refused() from None


@router.put("/profile", status_code=status.HTTP_200_OK)
async def put_academic_profile(
    request: Request, body: AcademicProfileUpdate, context: TenantContext = Depends(student)
) -> JSONResponse:
    try:
        profile = await service.replace(context.tenant_id, context.user_id, body.programme_id, body.level, body.course_ids)
    except NotAStudentMember:
        raise _refused() from None
    except UnavailableReferences as exc:
        # The same answer whether it doesn't exist, is another tenant's or is
        # archived: it names the field, never the value.
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", field),
                    "msg": "not available",
                    "input": None,
                    "ctx": {"error": ClientSafeError("is not available")},
                }
                for field in exc.fields
            ]
        ) from None
    return _envelope(request, profile)
