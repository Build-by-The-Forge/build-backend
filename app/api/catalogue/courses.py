from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.application.catalogue.course_service import CourseService
from app.api.catalogue.schemas import (
    CreateCourseRequest,
    CourseResponse,
    UpdateCourseRequest,
    CreateTopicRequest,
    UpdateTopicRequest,
)
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


@router.patch("/{course_id}", status_code=status.HTTP_200_OK)
async def update_course(
    course_id: str,
    request: Request,
    payload: UpdateCourseRequest,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_UPDATE)
    ),
) -> JSONResponse:
    course = await service.update_course(
        course_id=course_id,
        tenant_id=context.tenant_id,
        title=payload.title,
        description=payload.description,
    )
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="course not found"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": CourseResponse(
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
            ).model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{course_id}/publish", status_code=status.HTTP_200_OK)
async def publish_course(
    course_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_PUBLISH)
    ),
) -> JSONResponse:
    return await _transition_course(course_id, request, context, "publish")


@router.post("/{course_id}/archive", status_code=status.HTTP_200_OK)
async def archive_course(
    course_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_ARCHIVE)
    ),
) -> JSONResponse:
    return await _transition_course(course_id, request, context, "archive")


async def _transition_course(
    course_id: str,
    request: Request,
    context: TenantContext,
    transition: str,
) -> JSONResponse:
    course = await service.transition_course(
        course_id, context.tenant_id, transition
    )
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="course not found"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "id": course.id.value,
                "status": course.status.value,
            },
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{course_id}/topics", status_code=status.HTTP_201_CREATED)
async def create_topic(
    course_id: str,
    request: Request,
    payload: CreateTopicRequest,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_CREATE)
    ),
) -> JSONResponse:
    topic = await service.create_topic(
        course_id=course_id,
        title=payload.title,
        slug=payload.slug,
        description=payload.description,
        sequence=payload.sequence,
        tenant_id=context.tenant_id,
    )
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="course not found"
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": {
                "id": topic.id.value,
                "course_id": topic.course_id.value,
                "title": topic.title.value,
                "slug": topic.slug.value,
                "description": (
                    topic.description.value if topic.description is not None else None
                ),
                "sequence": topic.sequence.value,
                "status": topic.status.value,
            },
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{course_id}/topics", status_code=status.HTTP_200_OK)
async def list_topics(
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
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [
                {
                    "id": topic.id.value,
                    "course_id": topic.course_id.value,
                    "title": topic.title.value,
                    "slug": topic.slug.value,
                    "description": (
                        topic.description.value if topic.description is not None else None
                    ),
                    "sequence": topic.sequence.value,
                    "status": topic.status.value,
                }
                for topic in course.topics
            ],
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.patch("/topics/{topic_id}", status_code=status.HTTP_200_OK)
async def update_topic(
    topic_id: str,
    request: Request,
    payload: UpdateTopicRequest,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_UPDATE)
    ),
) -> JSONResponse:
    topic = await service.update_topic(
        topic_id=topic_id,
        tenant_id=context.tenant_id,
        title=payload.title,
        description=payload.description,
    )
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "id": topic.id.value,
                "course_id": topic.course_id.value,
                "title": topic.title.value,
                "slug": topic.slug.value,
                "description": topic.description.value if topic.description else None,
                "sequence": topic.sequence.value,
                "status": topic.status.value,
            },
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/topics/{topic_id}/archive", status_code=status.HTTP_200_OK)
async def archive_topic(
    topic_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_ARCHIVE)
    ),
) -> JSONResponse:
    topic = await service.transition_topic(topic_id, context.tenant_id, "archive")
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {"id": topic.id.value, "status": topic.status.value},
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )
