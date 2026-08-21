from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.application.catalogue.course_service import CourseService
from app.api.catalogue.schemas import CreateCourseRequest, CourseResponse
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext

router = APIRouter(prefix="/catalogue/courses", tags=["catalogue"])
container = build_container()
service = container.get(CourseService)


@router.get("/", status_code=status.HTTP_200_OK)
async def list_courses(
    request: Request,
    department_id: str | None = None,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_READ)
    ),
) -> JSONResponse:
    try:
        courses = await service.list_courses(
            department_id=department_id, tenant_id=context.tenant_id
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

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [
                {
                    "id": course.id.value,
                    "department_id": course.department_id.value,
                    "code": course.code.value,
                    "title": course.title.value,
                    "slug": course.slug.value,
                    "credit_units": course.credit_units.value,
                    "level": course.level.value,
                    "semester": course.semester.value,
                    "status": course.status.value,
                    "description": course.description,
                }
                for course in courses
            ],
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{course_id}", status_code=status.HTTP_200_OK)
async def get_course(
    course_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_READ)
    ),
) -> JSONResponse:
    course = await service.get_course(course_id, tenant_id=context.tenant_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="course not found"
        )

    response = CourseResponse(
        id=course.id.value,
        department_id=course.department_id.value,
        code=course.code.value,
        title=course.title.value,
        slug=course.slug.value,
        credit_units=course.credit_units.value,
        level=course.level.value,
        semester=course.semester.value,
        status=course.status.value,
        description=course.description,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": response.dict(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_course(
    request: Request,
    payload: CreateCourseRequest,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_CREATE)
    ),
) -> JSONResponse:
    try:
        course = await service.create_course(
            tenant_id=context.tenant_id,
            department_id=payload.department_id,
            code=payload.code,
            title=payload.title,
            slug=payload.slug,
            credit_units=payload.credit_units,
            level=payload.level,
            semester=payload.semester,
            description=payload.description,
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

    response = CourseResponse(
        id=course.id.value,
        department_id=course.department_id.value,
        code=course.code.value,
        title=course.title.value,
        slug=course.slug.value,
        credit_units=course.credit_units.value,
        level=course.level.value,
        semester=course.semester.value,
        status=course.status.value,
        description=course.description,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": response.dict(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )
