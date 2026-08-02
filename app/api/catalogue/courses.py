from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.application.catalogue.course_service import CourseService
from app.bootstrap.container import build_container

router = APIRouter(prefix="/catalogue/courses", tags=["catalogue"])
container = build_container()
service = container.get(CourseService)


@router.get("/", status_code=status.HTTP_200_OK)
async def list_courses(
    request: Request, department_id: str | None = None
) -> JSONResponse:
    try:
        courses = await service.list_courses(department_id=department_id)
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
