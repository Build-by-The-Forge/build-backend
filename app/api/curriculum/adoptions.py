from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.curriculum.adoption_schemas import (
    AdoptBenchmarkRequest,
    CreateOverrideRequest,
    CurriculumOverrideResponse,
    InstitutionalAdoptionResponse,
)
from app.api.curriculum.effective_schemas import (
    AppliedOverrideProvenanceResponse,
    EffectiveCourseResponse,
    EffectiveCurriculumResponse,
    EffectiveCurriculumStatisticsResponse,
    EffectiveOutcomeResponse,
    EffectiveTopicResponse,
    OmittedCourseResponse,
    StudentCourseResponse,
    StudentEffectiveCurriculumResponse,
    StudentOutcomeResponse,
    StudentTopicResponse,
)
from app.application.curriculum.institutional_adoption_service import (
    InstitutionalAdoptionService,
)
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.curriculum.adoption import (
    CurriculumOverride,
    InstitutionalAdoption,
)
from app.domain.curriculum.effective import (
    EffectiveCurriculum,
)

router = APIRouter(prefix="/curriculum/adoptions", tags=["curriculum-adoptions"])
service = build_container().get(InstitutionalAdoptionService)


@router.post("", status_code=status.HTTP_201_CREATED)
async def adopt_benchmark(
    payload: AdoptBenchmarkRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        adoption = await service.adopt_benchmark(
            tenant_id=context.tenant_id,
            programme_id=payload.programme_id,
            benchmark_curriculum_id=payload.benchmark_curriculum_id,
            actor_id=context.tenant_id,
            actor_email=f"{context.tenant_id}@build.internal",
            academic_session_id=payload.academic_session_id,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": _adoption_payload(adoption),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("", status_code=status.HTTP_200_OK)
async def list_adoptions(
    request: Request,
    programme_id: str | None = None,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    adoptions = await service.list_adoptions(
        tenant_id=context.tenant_id,
        programme_id=programme_id,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_adoption_payload(a) for a in adoptions],
            "meta": {"total": len(adoptions)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{adoption_id}", status_code=status.HTTP_200_OK)
async def get_adoption(
    adoption_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    try:
        adoption, overrides = await service.get_adoption_detail(
            adoption_id=adoption_id,
            tenant_id=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "adoption": _adoption_payload(adoption),
                "overrides": [_override_payload(o) for o in overrides],
            },
            "meta": {"overrides_count": len(overrides)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{adoption_id}/activate", status_code=status.HTTP_200_OK)
async def activate_adoption(
    adoption_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        adoption, superseded = await service.activate_adoption(
            adoption_id=adoption_id,
            tenant_id=context.tenant_id,
            actor_id=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "activated": _adoption_payload(adoption),
                "superseded": (_adoption_payload(superseded) if superseded is not None else None),
            },
            "meta": {"superseded_adoption_id": (superseded.id if superseded is not None else None)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{adoption_id}/overrides", status_code=status.HTTP_201_CREATED)
async def add_override(
    adoption_id: str,
    payload: CreateOverrideRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        override = await service.add_override(
            adoption_id=adoption_id,
            tenant_id=context.tenant_id,
            override_type=payload.override_type,
            reason=payload.reason,
            actor_id=context.tenant_id,
            actor_email=f"{context.tenant_id}@build.internal",
            target_course_code=payload.target_course_code,
            target_topic_id=payload.target_topic_id,
            target_outcome_id=payload.target_outcome_id,
            field_overrides=payload.field_overrides,
            custom_payload=payload.custom_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": _override_payload(override),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.delete("/{adoption_id}/overrides/{override_id}", status_code=status.HTTP_200_OK)
async def remove_override(
    adoption_id: str,
    override_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_MANAGE)),
) -> JSONResponse:
    try:
        deleted = await service.remove_override(
            adoption_id=adoption_id,
            override_id=override_id,
            tenant_id=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="override not found or already deleted",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"deleted": True, "override_id": override_id},
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{adoption_id}/effective", status_code=status.HTTP_200_OK)
async def get_effective_curriculum_by_adoption(
    adoption_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CURRICULUM_SOURCE_READ)),
) -> JSONResponse:
    try:
        effective = await service.get_effective_curriculum(
            adoption_id=adoption_id,
            tenant_id=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _effective_curriculum_payload(effective),
            "meta": {
                "effective_curriculum_fingerprint": effective.effective_curriculum_fingerprint,
                "resolution_engine_version": effective.resolution_engine_version,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/effective/active/{programme_id}", status_code=status.HTTP_200_OK)
async def get_active_effective_curriculum_student(
    programme_id: str,
    request: Request,
    academic_session_id: str | None = None,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    try:
        effective = await service.get_active_effective_curriculum(
            tenant_id=context.tenant_id,
            programme_id=programme_id,
            academic_session_id=academic_session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _student_effective_curriculum_payload(effective),
            "meta": {
                "effective_curriculum_fingerprint": effective.effective_curriculum_fingerprint,
                "resolution_engine_version": effective.resolution_engine_version,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _adoption_payload(adoption: InstitutionalAdoption) -> dict[str, object]:
    return InstitutionalAdoptionResponse(
        id=adoption.id,
        tenant_id=adoption.tenant_id,
        programme_id=adoption.programme_id,
        benchmark_curriculum_id=adoption.benchmark_curriculum_id,
        benchmark_version=adoption.benchmark_version,
        benchmark_fingerprint=adoption.benchmark_fingerprint,
        academic_session_id=adoption.academic_session_id,
        status=adoption.status.value,
        notes=adoption.notes,
        adopted_by=adoption.adopted_by,
        adopted_by_email=adoption.adopted_by_email,
        created_at=adoption.created_at.isoformat(),
        updated_at=adoption.updated_at.isoformat(),
    ).model_dump()


def _override_payload(override: CurriculumOverride) -> dict[str, object]:
    return CurriculumOverrideResponse(
        id=override.id,
        adoption_id=override.adoption_id,
        override_type=override.override_type.value,
        target_course_code=override.target_course_code,
        target_topic_id=override.target_topic_id,
        target_outcome_id=override.target_outcome_id,
        field_overrides=override.field_overrides,
        custom_payload=override.custom_payload,
        reason=override.reason,
        created_by=override.created_by,
        created_by_email=override.created_by_email,
        created_at=override.created_at.isoformat(),
    ).model_dump()


def _effective_curriculum_payload(
    effective: EffectiveCurriculum,
) -> dict[str, object]:
    courses_payload: list[EffectiveCourseResponse] = []
    for c in effective.courses:
        topics_payload: list[EffectiveTopicResponse] = []
        for t in c.topics:
            outcomes_payload = [
                EffectiveOutcomeResponse(
                    id=o.id,
                    sequence=o.sequence,
                    description=o.description,
                    bloom_level=o.bloom_level.value,
                    origin=o.origin.value,
                    applied_overrides=[
                        AppliedOverrideProvenanceResponse(
                            override_id=p.override_id,
                            override_type=p.override_type,
                            reason=p.reason,
                            field_overrides=p.field_overrides,
                            created_by_email=p.created_by_email,
                            created_at=p.created_at.isoformat(),
                        )
                        for p in o.applied_overrides
                    ],
                )
                for o in t.outcomes
            ]
            topics_payload.append(
                EffectiveTopicResponse(
                    id=t.id,
                    sequence=t.sequence,
                    title=t.title,
                    description=t.description,
                    origin=t.origin.value,
                    outcomes=outcomes_payload,
                    applied_overrides=[
                        AppliedOverrideProvenanceResponse(
                            override_id=p.override_id,
                            override_type=p.override_type,
                            reason=p.reason,
                            field_overrides=p.field_overrides,
                            created_by_email=p.created_by_email,
                            created_at=p.created_at.isoformat(),
                        )
                        for p in t.applied_overrides
                    ],
                )
            )

        courses_payload.append(
            EffectiveCourseResponse(
                code=c.code,
                title=c.title,
                credit_units=c.credit_units,
                level=c.level,
                semester=c.semester,
                sequence=c.sequence,
                is_compulsory=c.is_compulsory,
                course_category=c.course_category,
                description=c.description,
                origin=c.origin.value,
                topics=topics_payload,
                applied_overrides=[
                    AppliedOverrideProvenanceResponse(
                        override_id=p.override_id,
                        override_type=p.override_type,
                        reason=p.reason,
                        field_overrides=p.field_overrides,
                        created_by_email=p.created_by_email,
                        created_at=p.created_at.isoformat(),
                    )
                    for p in c.applied_overrides
                ],
                benchmark_course_id=c.benchmark_course_id,
            )
        )

    omitted_payload = [
        OmittedCourseResponse(
            code=o.code,
            title=o.title,
            credit_units=o.credit_units,
            level=o.level,
            semester=o.semester,
            reason=o.reason,
            override_id=o.override_id,
            created_by_email=o.created_by_email,
            benchmark_course_id=o.benchmark_course_id,
        )
        for o in effective.omitted_courses
    ]

    stats_payload = EffectiveCurriculumStatisticsResponse(
        total_credit_units=effective.statistics.total_credit_units,
        total_courses=effective.statistics.total_courses,
        national_courses_count=effective.statistics.national_courses_count,
        modified_courses_count=effective.statistics.modified_courses_count,
        custom_courses_count=effective.statistics.custom_courses_count,
        omitted_courses_count=effective.statistics.omitted_courses_count,
    )

    return EffectiveCurriculumResponse(
        adoption_id=effective.adoption_id,
        tenant_id=effective.tenant_id,
        programme_id=effective.programme_id,
        academic_session_id=effective.academic_session_id,
        benchmark_curriculum_id=effective.benchmark_curriculum_id,
        benchmark_version=effective.benchmark_version,
        benchmark_fingerprint=effective.benchmark_fingerprint,
        effective_curriculum_fingerprint=effective.effective_curriculum_fingerprint,
        resolution_engine_version=effective.resolution_engine_version,
        status=effective.status.value,
        statistics=stats_payload,
        courses=courses_payload,
        omitted_courses=omitted_payload,
    ).model_dump()


def _student_effective_curriculum_payload(
    effective: EffectiveCurriculum,
) -> dict[str, object]:
    courses_payload: list[StudentCourseResponse] = []
    for c in effective.courses:
        topics_payload = [
            StudentTopicResponse(
                sequence=t.sequence,
                title=t.title,
                description=t.description,
                outcomes=[
                    StudentOutcomeResponse(
                        sequence=o.sequence,
                        description=o.description,
                        bloom_level=o.bloom_level.value,
                    )
                    for o in t.outcomes
                ],
            )
            for t in c.topics
        ]
        courses_payload.append(
            StudentCourseResponse(
                code=c.code,
                title=c.title,
                credit_units=c.credit_units,
                level=c.level,
                semester=c.semester,
                is_compulsory=c.is_compulsory,
                course_category=c.course_category,
                description=c.description,
                origin=c.origin.value,
                topics=topics_payload,
            )
        )

    return StudentEffectiveCurriculumResponse(
        programme_id=effective.programme_id,
        academic_session_id=effective.academic_session_id,
        benchmark_version=effective.benchmark_version,
        effective_curriculum_fingerprint=effective.effective_curriculum_fingerprint,
        total_credit_units=effective.statistics.total_credit_units,
        total_courses=effective.statistics.total_courses,
        courses=courses_payload,
    ).model_dump()
