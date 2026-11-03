from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.catalogue.schemas import (
    CourseResponse,
    CreateCourseRequest,
    CreateLearningOutcomeRequest,
    CreateReferenceMaterialRequest,
    CreateTopicRequest,
    IdFilter,
    IdInPath,
    UpdateCourseRequest,
    UpdateLearningOutcomeRequest,
    UpdateReferenceMaterialRequest,
    UpdateTopicRequest,
)
from app.api.pagination import Page
from app.application.catalogue.course_service import CourseService
from app.bootstrap.container import build_container
from app.core.authorization import Permission, authorization
from app.core.dependencies import require_permission
from app.core.exceptions import ClientHTTPException, public_message
from app.core.tenant_context import TenantContext
from app.domain.catalogue.course import Course
from app.domain.catalogue.errors import (
    CatalogueParentArchivedError,
    CourseAlreadyArchivedError,
    LearningOutcomeAlreadyArchivedError,
    ReferenceMaterialAlreadyArchivedError,
    TopicAlreadyArchivedError,
)
from app.domain.catalogue.reference_material import ReferenceMaterial
from app.domain.catalogue.topic import Topic
from app.domain.catalogue.value_objects import CourseStatus, LearningOutcomeStatus, ReferenceMaterialStatus, TopicStatus
from app.domain.client_safe import ClientSafeError

router = APIRouter(prefix="/catalogue/courses", tags=["catalogue"])
topic_router = APIRouter(prefix="/catalogue/topics", tags=["catalogue"])
learning_outcome_router = APIRouter(prefix="/catalogue/learning-outcomes", tags=["catalogue"])
reference_router = APIRouter(prefix="/catalogue/reference-materials", tags=["catalogue"])
container = build_container()
service = container.get(CourseService)

P = ParamSpec("P")


def _answers_refusals(route: Callable[P, Awaitable[JSONResponse]]) -> Callable[P, Awaitable[JSONResponse]]:
    """For a route that takes what a client wrote: a domain rule refusing it is the caller's
    to fix. Only here, not globally, since a marked error can also come from an internal
    invariant. A stored row breaking a rule arrives as StoredCourseInvalidError, not as a
    marked error, so it stays a server failure here too."""

    @wraps(route)
    async def answering(*args: P.args, **kwargs: P.kwargs) -> JSONResponse:
        try:
            return await route(*args, **kwargs)
        except ClientSafeError as exc:
            raise ClientHTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=public_message(exc)) from exc

    return answering


def _is_unique_violation(exc: IntegrityError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == "23505" or "UNIQUE constraint failed" in str(exc.orig)


def _answers_conflicts(route: Callable[P, Awaitable[JSONResponse]]) -> Callable[P, Awaitable[JSONResponse]]:
    """The request is fine but the catalogue's current state refuses it: already archived,
    or a code, slug or sequence that's taken. The database's constraints decide the second,
    so two racing requests get the same answer as two in a row."""

    @wraps(route)
    async def answering(*args: P.args, **kwargs: P.kwargs) -> JSONResponse:
        try:
            return await route(*args, **kwargs)
        except CatalogueParentArchivedError as exc:
            raise ClientHTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="nothing new can be added to something archived"
            ) from exc
        except (
            CourseAlreadyArchivedError,
            TopicAlreadyArchivedError,
            LearningOutcomeAlreadyArchivedError,
            ReferenceMaterialAlreadyArchivedError,
        ) as exc:
            raise ClientHTTPException(status_code=status.HTTP_409_CONFLICT, detail="this is already archived") from exc
        except IntegrityError as exc:
            if not _is_unique_violation(exc):
                raise
            raise ClientHTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="this conflicts with an existing catalogue record"
            ) from exc

    return answering


def _sees_archived(context: TenantContext) -> bool:
    """Whoever can change the catalogue sees all of it. Everyone else sees only what's active."""
    return authorization.can(context, Permission.CATALOGUE_UPDATE)


def _lists_archived(context: TenantContext, include_archived: bool) -> bool:
    """A list holds only what's active, for everyone, as the contract says. Staff who need
    the rest ask for it; anyone else asking is refused rather than quietly ignored."""
    if include_archived and not _sees_archived(context):
        raise ClientHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
    return include_archived


async def _visible_to_readers(course: Course, tenant_id: str) -> bool:
    """A course is out of reach if it's archived, or if the hierarchy above it is."""
    return course.status is CourseStatus.ACTIVE and await service.has_active_department(course.department_id.value, tenant_id)


async def _readable_course(course_id: str, context: TenantContext) -> Course:
    course = await service.get_course(course_id, tenant_id=context.tenant_id)
    if course is None or not (_sees_archived(context) or await _visible_to_readers(course, context.tenant_id)):
        raise ClientHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found")
    return course


async def _readable_topic(topic_id: str, context: TenantContext) -> tuple[Course, Topic]:
    """A topic is out of reach if it or its course is archived, for whoever can't see those."""
    course = await service.get_course_by_topic(topic_id, context.tenant_id)
    topic = next((item for item in course.topics if item.id.value == topic_id), None) if course else None
    if course is None or topic is None:
        raise ClientHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic not found")
    if not _sees_archived(context) and (
        topic.status is not TopicStatus.ACTIVE or not await _visible_to_readers(course, context.tenant_id)
    ):
        raise ClientHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic not found")
    return course, topic


@router.get("", status_code=status.HTTP_200_OK)
@router.get("/", status_code=status.HTTP_200_OK, include_in_schema=False)
async def list_courses(
    request: Request,
    page: Page,
    department_id: IdFilter = None,
    include_archived: bool = False,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    courses, total = await service.list_courses(
        tenant_id=context.tenant_id,
        department_id=department_id,
        active_only=not _lists_archived(context, include_archived),
        limit=page.limit,
        offset=page.offset,
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
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None), "pagination": page.meta(total)},
        },
    )


@router.get("/{course_id}", status_code=status.HTTP_200_OK)
async def get_course(
    course_id: IdInPath,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    course = await _readable_course(course_id, context)

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
            "data": response.model_dump(),
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
@_answers_refusals
@_answers_conflicts
async def create_course(
    request: Request,
    payload: CreateCourseRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_CREATE)),
) -> JSONResponse:
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
            "data": response.model_dump(),
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.patch("/{course_id}", status_code=status.HTTP_200_OK)
@_answers_refusals
@_answers_conflicts
async def update_course(
    course_id: IdInPath,
    request: Request,
    payload: UpdateCourseRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_UPDATE)),
) -> JSONResponse:
    course = await service.update_course(
        course_id=course_id,
        tenant_id=context.tenant_id,
        title=payload.title,
        description=payload.description,
    )
    if course is None:
        raise ClientHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found")
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
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.post("/{course_id}/publish", status_code=status.HTTP_200_OK)
async def publish_course(
    course_id: IdInPath,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_PUBLISH)),
) -> JSONResponse:
    return await _transition_course(course_id, request, context, "publish")


@router.post("/{course_id}/archive", status_code=status.HTTP_200_OK)
async def archive_course(
    course_id: IdInPath,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_ARCHIVE)),
) -> JSONResponse:
    return await _transition_course(course_id, request, context, "archive")


@_answers_conflicts
async def _transition_course(
    course_id: IdInPath,
    request: Request,
    context: TenantContext,
    transition: str,
) -> JSONResponse:
    course = await service.transition_course(course_id, context.tenant_id, transition)
    if course is None:
        raise ClientHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "id": course.id.value,
                "status": course.status.value,
            },
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.post("/{course_id}/topics", status_code=status.HTTP_201_CREATED)
@_answers_refusals
@_answers_conflicts
async def create_topic(
    course_id: IdInPath,
    request: Request,
    payload: CreateTopicRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_CREATE)),
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
        raise ClientHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": {
                "id": topic.id.value,
                "course_id": topic.course_id.value,
                "title": topic.title.value,
                "slug": topic.slug.value,
                "description": (topic.description.value if topic.description is not None else None),
                "sequence": topic.sequence.value,
                "status": topic.status.value,
            },
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@router.get("/{course_id}/topics", status_code=status.HTTP_200_OK)
async def list_topics(
    course_id: IdInPath,
    request: Request,
    page: Page,
    include_archived: bool = False,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    archived_too = _lists_archived(context, include_archived)
    course = await _readable_course(course_id, context)
    topics = sorted(
        (topic for topic in course.topics if archived_too or topic.status is TopicStatus.ACTIVE),
        key=lambda topic: (topic.sequence.value, topic.id.value),
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
                    "description": (topic.description.value if topic.description is not None else None),
                    "sequence": topic.sequence.value,
                    "status": topic.status.value,
                }
                for topic in page.slice(topics)
            ],
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None), "pagination": page.meta(len(topics))},
        },
    )


@topic_router.patch("/{topic_id}", status_code=status.HTTP_200_OK)
@_answers_refusals
@_answers_conflicts
async def update_topic(
    topic_id: IdInPath,
    request: Request,
    payload: UpdateTopicRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_UPDATE)),
) -> JSONResponse:
    topic = await service.update_topic(
        topic_id=topic_id,
        tenant_id=context.tenant_id,
        title=payload.title,
        description=payload.description,
    )
    if topic is None:
        raise ClientHTTPException(status_code=404, detail="topic not found")
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
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@topic_router.post("/{topic_id}/archive", status_code=status.HTTP_200_OK)
@_answers_conflicts
async def archive_topic(
    topic_id: IdInPath,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_ARCHIVE)),
) -> JSONResponse:
    topic = await service.transition_topic(topic_id, context.tenant_id, "archive")
    if topic is None:
        raise ClientHTTPException(status_code=404, detail="topic not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {"id": topic.id.value, "status": topic.status.value},
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@topic_router.post("/{topic_id}/learning-outcomes", status_code=status.HTTP_201_CREATED)
@_answers_refusals
@_answers_conflicts
async def create_learning_outcome(
    topic_id: IdInPath,
    request: Request,
    payload: CreateLearningOutcomeRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_CREATE)),
) -> JSONResponse:
    outcome = await service.create_learning_outcome(
        topic_id=topic_id,
        sequence=payload.sequence,
        description=payload.description,
        tenant_id=context.tenant_id,
    )
    if outcome is None:
        raise ClientHTTPException(status_code=404, detail="topic not found")
    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "data": {
                "id": outcome.id.value,
                "topic_id": outcome.topic_id.value,
                "sequence": outcome.sequence.value,
                "description": outcome.description.value,
                "status": outcome.status.value,
            },
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@topic_router.get("/{topic_id}/learning-outcomes", status_code=status.HTTP_200_OK)
async def list_learning_outcomes(
    topic_id: IdInPath,
    request: Request,
    page: Page,
    include_archived: bool = False,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    archived_too = _lists_archived(context, include_archived)
    _, topic = await _readable_topic(topic_id, context)
    outcomes = sorted(
        (outcome for outcome in topic.learning_outcomes if archived_too or outcome.status is LearningOutcomeStatus.ACTIVE),
        key=lambda outcome: (outcome.sequence.value, outcome.id.value),
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": [
                {
                    "id": outcome.id.value,
                    "topic_id": outcome.topic_id.value,
                    "sequence": outcome.sequence.value,
                    "description": outcome.description.value,
                    "status": outcome.status.value,
                }
                for outcome in page.slice(outcomes)
            ],
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None), "pagination": page.meta(len(outcomes))},
        },
    )


@learning_outcome_router.patch("/{learning_outcome_id}", status_code=status.HTTP_200_OK)
@_answers_refusals
@_answers_conflicts
async def update_learning_outcome(
    learning_outcome_id: IdInPath,
    request: Request,
    payload: UpdateLearningOutcomeRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_UPDATE)),
) -> JSONResponse:
    outcome = await service.update_learning_outcome(
        learning_outcome_id,
        description=payload.description,
        tenant_id=context.tenant_id,
    )
    if outcome is None:
        raise ClientHTTPException(status_code=404, detail="learning outcome not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "id": outcome.id.value,
                "topic_id": outcome.topic_id.value,
                "sequence": outcome.sequence.value,
                "description": outcome.description.value,
                "status": outcome.status.value,
            },
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@learning_outcome_router.post("/{learning_outcome_id}/archive", status_code=status.HTTP_200_OK)
@_answers_conflicts
async def archive_learning_outcome(
    learning_outcome_id: IdInPath,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_ARCHIVE)),
) -> JSONResponse:
    outcome = await service.transition_learning_outcome(learning_outcome_id, context.tenant_id, "archive")
    if outcome is None:
        raise ClientHTTPException(status_code=404, detail="learning outcome not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {"id": outcome.id.value, "status": outcome.status.value},
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@topic_router.post("/{topic_id}/reference-materials", status_code=status.HTTP_201_CREATED)
@_answers_refusals
@_answers_conflicts
async def create_reference_material(
    topic_id: IdInPath,
    request: Request,
    payload: CreateReferenceMaterialRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_CREATE)),
) -> JSONResponse:
    material = await service.create_reference_material(
        topic_id=topic_id,
        title=payload.title,
        material_type=payload.material_type,
        url=payload.url,
        tenant_id=context.tenant_id,
    )
    if material is None:
        raise ClientHTTPException(status_code=404, detail="topic not found")
    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "data": _reference_material_payload(material),
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@topic_router.get("/{topic_id}/reference-materials", status_code=status.HTTP_200_OK)
async def list_reference_materials(
    topic_id: IdInPath,
    request: Request,
    page: Page,
    include_archived: bool = False,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    archived_too = _lists_archived(context, include_archived)
    course, _ = await _readable_topic(topic_id, context)
    materials = sorted(
        (material for material in course.references if archived_too or material.status is ReferenceMaterialStatus.ACTIVE),
        key=lambda material: (material.title.value, material.id.value),
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": [_reference_material_payload(item) for item in page.slice(materials)],
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None), "pagination": page.meta(len(materials))},
        },
    )


@reference_router.patch("/{reference_material_id}", status_code=status.HTTP_200_OK)
@_answers_refusals
@_answers_conflicts
async def update_reference_material(
    reference_material_id: IdInPath,
    request: Request,
    payload: UpdateReferenceMaterialRequest,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_UPDATE)),
) -> JSONResponse:
    material = await service.update_reference_material(
        reference_material_id,
        title=payload.title,
        material_type=payload.material_type,
        url=payload.url,
        tenant_id=context.tenant_id,
    )
    if material is None:
        raise ClientHTTPException(status_code=404, detail="reference material not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": _reference_material_payload(material),
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


@reference_router.post("/{reference_material_id}/archive", status_code=status.HTTP_200_OK)
@_answers_conflicts
async def archive_reference_material(
    reference_material_id: IdInPath,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_ARCHIVE)),
) -> JSONResponse:
    material = await service.transition_reference_material(reference_material_id, context.tenant_id, "archive")
    if material is None:
        raise ClientHTTPException(status_code=404, detail="reference material not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {"id": material.id.value, "status": material.status.value},
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
        },
    )


def _reference_material_payload(material: ReferenceMaterial) -> dict[str, object]:
    return {
        "id": material.id.value,
        "course_id": material.course_id.value,
        "title": material.title.value,
        "material_type": material.material_type.value,
        "url": material.url.value if material.url is not None else None,
        "status": material.status.value,
    }
