from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.curriculum.benchmark_schemas import (
    ApproveBenchmarkRequest,
    BenchmarkAuditLogResponse,
    BenchmarkCourseDetailResponse,
    BenchmarkCourseSummaryResponse,
    BenchmarkCurriculumDiffResponse,
    BenchmarkCurriculumSummaryResponse,
    BenchmarkOutcomeResponse,
    BenchmarkTopicResponse,
    CourseDiffResponse,
    DiffStatisticsResponse,
    FieldDiffResponse,
    IngestBenchmarkCandidateRequest,
    OutcomeDiffResponse,
    RejectBenchmarkRequest,
    ReviseBenchmarkRequest,
    SubmitReviewRequest,
    TopicDiffResponse,
    ValidationIssueResponse,
    ValidationResultResponse,
)
from app.application.curriculum.benchmark_commands import (
    BenchmarkCourseInput,
    BenchmarkOutcomeInput,
    BenchmarkTopicInput,
)
from app.application.curriculum.benchmark_service import (
    BenchmarkCurriculumService,
)
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.curriculum.audit import BenchmarkAuditLog
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
)
from app.domain.curriculum.diff import BenchmarkCurriculumDiff
from app.domain.curriculum.validator import ValidationResult

router = APIRouter(prefix="/curriculum/benchmarks", tags=["curriculum-benchmarks"])
service = build_container().get(BenchmarkCurriculumService)


@router.post("/candidate", status_code=status.HTTP_201_CREATED)
async def ingest_candidate(
    payload: IngestBenchmarkCandidateRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    courses = []
    for c in payload.courses:
        topics = []
        for t in c.topics:
            outcomes = [
                BenchmarkOutcomeInput(
                    sequence=o.sequence,
                    description=o.description,
                    bloom_level=o.bloom_level,
                )
                for o in t.outcomes
            ]
            topics.append(
                BenchmarkTopicInput(
                    sequence=t.sequence,
                    title=t.title,
                    description=t.description,
                    outcomes=outcomes,
                )
            )
        courses.append(
            BenchmarkCourseInput(
                code=c.code,
                title=c.title,
                credit_units=c.credit_units,
                level=c.level,
                semester=c.semester,
                sequence=c.sequence,
                is_compulsory=c.is_compulsory,
                course_category=c.course_category,
                description=c.description,
                topics=topics,
            )
        )

    try:
        curriculum, created = await service.ingest_candidate(
            source_snapshot_id=payload.source_snapshot_id,
            extractor_version=payload.extractor_version,
            discipline_group=payload.discipline_group,
            programme_name=payload.programme_name,
            programme_code=payload.programme_code,
            version=payload.version,
            degree_level=payload.degree_level,
            minimum_credit_units=payload.minimum_credit_units,
            courses=courses,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": _curriculum_summary_payload(curriculum),
            "meta": {"created": created},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("", status_code=status.HTTP_200_OK)
async def list_benchmarks(
    request: Request,
    programme_code: str | None = None,
    status_filter: str | None = None,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    curricula = await service.list_curricula(programme_code=programme_code, status=status_filter)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_curriculum_summary_payload(c) for c in curricula],
            "meta": {"total": len(curricula)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/diff", status_code=status.HTTP_200_OK)
async def compare_benchmarks(
    source_id: str,
    target_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    try:
        diff = await service.compare_curricula(
            source_curriculum_id=source_id,
            target_curriculum_id=target_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _diff_payload(diff),
            "meta": {
                "fingerprint": diff.diff_fingerprint,
                "credit_delta": diff.statistics.credit_units_delta,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{curriculum_id}", status_code=status.HTTP_200_OK)
async def get_benchmark(
    curriculum_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    curriculum = await service.get_curriculum(curriculum_id)
    if curriculum is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="benchmark curriculum not found",
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _curriculum_summary_payload(curriculum),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{curriculum_id}/courses", status_code=status.HTTP_200_OK)
async def list_courses(
    curriculum_id: str,
    request: Request,
    level: int | None = None,
    semester: int | None = None,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    curriculum = await service.get_curriculum(curriculum_id)
    if curriculum is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="benchmark curriculum not found",
        )

    courses = await service.list_courses(curriculum_id=curriculum_id, level=level, semester=semester)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_course_summary_payload(c) for c in courses],
            "meta": {
                "curriculum_id": curriculum_id,
                "total": len(courses),
                "level": level,
                "semester": semester,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{curriculum_id}/courses/{course_id}", status_code=status.HTTP_200_OK)
async def get_course_detail(
    curriculum_id: str,
    course_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    course = await service.get_course(course_id)
    if course is None or course.benchmark_curriculum_id != curriculum_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="benchmark course not found",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _course_detail_payload(course),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{curriculum_id}/validate", status_code=status.HTTP_200_OK)
async def validate_candidate(
    curriculum_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        curriculum, validation_result = await service.validate_candidate(curriculum_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "curriculum": _curriculum_summary_payload(curriculum),
                "validation": _validation_result_payload(validation_result),
            },
            "meta": {
                "is_valid": validation_result.is_valid,
                "error_count": validation_result.error_count,
                "warning_count": validation_result.warning_count,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{curriculum_id}/submit-review", status_code=status.HTTP_200_OK)
async def submit_for_review(
    curriculum_id: str,
    payload: SubmitReviewRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        curriculum, audit_log = await service.submit_for_review(
            curriculum_id=curriculum_id,
            actor_id=context.tenant_id,
            actor_email=f"{context.tenant_id}@build.internal",
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "curriculum": _curriculum_summary_payload(curriculum),
                "audit_log": _audit_log_payload(audit_log),
            },
            "meta": {
                "diff_fingerprint": audit_log.diff_fingerprint,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{curriculum_id}/approve", status_code=status.HTTP_200_OK)
async def approve_curriculum(
    curriculum_id: str,
    payload: ApproveBenchmarkRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        curriculum, audit_log = await service.approve_curriculum(
            curriculum_id=curriculum_id,
            reviewer_id=context.tenant_id,
            reviewer_email=f"{context.tenant_id}@build.internal",
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "curriculum": _curriculum_summary_payload(curriculum),
                "audit_log": _audit_log_payload(audit_log),
            },
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{curriculum_id}/reject", status_code=status.HTTP_200_OK)
async def reject_curriculum(
    curriculum_id: str,
    payload: RejectBenchmarkRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        curriculum, audit_log = await service.reject_curriculum(
            curriculum_id=curriculum_id,
            reviewer_id=context.tenant_id,
            reviewer_email=f"{context.tenant_id}@build.internal",
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "curriculum": _curriculum_summary_payload(curriculum),
                "audit_log": _audit_log_payload(audit_log),
            },
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{curriculum_id}/revise", status_code=status.HTTP_200_OK)
async def revise_curriculum(
    curriculum_id: str,
    payload: ReviseBenchmarkRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        curriculum, audit_log = await service.revise_curriculum(
            curriculum_id=curriculum_id,
            actor_id=context.tenant_id,
            actor_email=f"{context.tenant_id}@build.internal",
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "curriculum": _curriculum_summary_payload(curriculum),
                "audit_log": _audit_log_payload(audit_log),
            },
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{curriculum_id}/audit-trail", status_code=status.HTTP_200_OK)
async def get_audit_trail(
    curriculum_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    audit_logs = await service.get_audit_trail(curriculum_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_audit_log_payload(log) for log in audit_logs],
            "meta": {"total": len(audit_logs)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{curriculum_id}/activate", status_code=status.HTTP_200_OK)
async def activate_curriculum(
    curriculum_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        curriculum, superseded = await service.activate_curriculum(
            curriculum_id=curriculum_id,
            activated_by=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "activated": _curriculum_summary_payload(curriculum),
                "superseded": (_curriculum_summary_payload(superseded) if superseded is not None else None),
            },
            "meta": {"superseded_curriculum_id": (superseded.id if superseded is not None else None)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get(
    "/active/{discipline_group}/{programme_code}",
    status_code=status.HTTP_200_OK,
)
async def get_active_benchmark(
    discipline_group: str,
    programme_code: str,
    request: Request,
    degree_level: str = "undergraduate",
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    curriculum = await service.get_active_curriculum(
        discipline_group=discipline_group,
        programme_code=programme_code,
        degree_level=degree_level,
    )
    if curriculum is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no active benchmark found for {discipline_group}/{programme_code} ({degree_level})",
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _curriculum_summary_payload(curriculum),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _curriculum_summary_payload(
    curriculum: BenchmarkCurriculum,
) -> dict[str, object]:
    return BenchmarkCurriculumSummaryResponse(
        id=curriculum.id,
        source_snapshot_id=curriculum.source_snapshot_id,
        discipline_group=curriculum.discipline_group,
        programme_name=curriculum.programme_name,
        programme_code=curriculum.programme_code,
        degree_level=curriculum.degree_level,
        version=curriculum.version,
        minimum_credit_units=curriculum.minimum_credit_units,
        status=curriculum.status.value,
        created_at=curriculum.created_at.isoformat(),
        updated_at=curriculum.updated_at.isoformat(),
    ).model_dump()


def _course_summary_payload(course: BenchmarkCourse) -> dict[str, object]:
    return BenchmarkCourseSummaryResponse(
        id=course.id,
        benchmark_curriculum_id=course.benchmark_curriculum_id,
        code=course.code,
        title=course.title,
        credit_units=course.credit_units,
        level=course.level,
        semester=course.semester,
        is_compulsory=course.is_compulsory,
        course_category=course.course_category,
        description=course.description,
        sequence=course.sequence,
    ).model_dump()


def _course_detail_payload(course: BenchmarkCourse) -> dict[str, object]:
    topics = []
    for t in course.topics:
        outcomes = [
            BenchmarkOutcomeResponse(
                id=o.id,
                sequence=o.sequence,
                description=o.description,
                bloom_level=o.bloom_level.value if o.bloom_level else None,
            )
            for o in t.outcomes
        ]
        topics.append(
            BenchmarkTopicResponse(
                id=t.id,
                sequence=t.sequence,
                title=t.title,
                description=t.description,
                outcomes=outcomes,
            )
        )

    return BenchmarkCourseDetailResponse(
        id=course.id,
        benchmark_curriculum_id=course.benchmark_curriculum_id,
        code=course.code,
        title=course.title,
        credit_units=course.credit_units,
        level=course.level,
        semester=course.semester,
        is_compulsory=course.is_compulsory,
        course_category=course.course_category,
        description=course.description,
        sequence=course.sequence,
        topics=topics,
    ).model_dump()


def _validation_result_payload(
    result: ValidationResult,
) -> dict[str, object]:
    issues = [
        ValidationIssueResponse(
            entity_type=i.entity_type,
            entity_identifier=i.entity_identifier,
            field=i.field,
            rule=i.rule,
            message=i.message,
            severity=i.severity.value,
        )
        for i in result.issues
    ]
    return ValidationResultResponse(
        is_valid=result.is_valid,
        error_count=result.error_count,
        warning_count=result.warning_count,
        issues=issues,
    ).model_dump()


def _diff_payload(diff: BenchmarkCurriculumDiff) -> dict[str, object]:
    course_diffs = []
    for c in diff.course_diffs:
        field_diffs = [
            FieldDiffResponse(
                field=f.field,
                old_value=f.old_value,
                new_value=f.new_value,
            )
            for f in c.field_diffs
        ]
        topic_diffs = []
        for t in c.topic_diffs:
            t_field_diffs = [
                FieldDiffResponse(
                    field=f.field,
                    old_value=f.old_value,
                    new_value=f.new_value,
                )
                for f in t.field_diffs
            ]
            o_diffs = [
                OutcomeDiffResponse(
                    sequence=o.sequence,
                    action=o.action.value,
                    description=o.description,
                    field_diffs=[
                        FieldDiffResponse(
                            field=f.field,
                            old_value=f.old_value,
                            new_value=f.new_value,
                        )
                        for f in o.field_diffs
                    ],
                )
                for o in t.outcome_diffs
            ]
            topic_diffs.append(
                TopicDiffResponse(
                    sequence=t.sequence,
                    title=t.title,
                    action=t.action.value,
                    field_diffs=t_field_diffs,
                    outcome_diffs=o_diffs,
                )
            )
        course_diffs.append(
            CourseDiffResponse(
                code=c.code,
                title=c.title,
                action=c.action.value,
                field_diffs=field_diffs,
                topic_diffs=topic_diffs,
            )
        )

    stats = DiffStatisticsResponse(
        courses_added=diff.statistics.courses_added,
        courses_removed=diff.statistics.courses_removed,
        courses_modified=diff.statistics.courses_modified,
        topics_added=diff.statistics.topics_added,
        topics_removed=diff.statistics.topics_removed,
        topics_modified=diff.statistics.topics_modified,
        outcomes_added=diff.statistics.outcomes_added,
        outcomes_removed=diff.statistics.outcomes_removed,
        outcomes_modified=diff.statistics.outcomes_modified,
        credit_units_before=diff.statistics.credit_units_before,
        credit_units_after=diff.statistics.credit_units_after,
        credit_units_delta=diff.statistics.credit_units_delta,
    )

    return BenchmarkCurriculumDiffResponse(
        source_curriculum_id=diff.source_curriculum_id,
        target_curriculum_id=diff.target_curriculum_id,
        source_version=diff.source_version,
        target_version=diff.target_version,
        discipline_group=diff.discipline_group,
        programme_code=diff.programme_code,
        degree_level=diff.degree_level,
        diff_fingerprint=diff.diff_fingerprint,
        statistics=stats,
        course_diffs=course_diffs,
    ).model_dump()


def _audit_log_payload(log: BenchmarkAuditLog) -> dict[str, object]:
    return BenchmarkAuditLogResponse(
        id=log.id,
        curriculum_id=log.curriculum_id,
        action=log.action.value,
        actor_id=log.actor_id,
        actor_email=log.actor_email,
        previous_status=log.previous_status,
        new_status=log.new_status,
        reason=log.reason,
        review_notes=log.review_notes,
        diff_fingerprint=log.diff_fingerprint,
        metadata=log.metadata_payload,
        created_at=log.created_at.isoformat(),
    ).model_dump()
