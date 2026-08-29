from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domain.curriculum.adoption import (
    AdoptionStatus,
    CurriculumOverride,
    InstitutionalAdoption,
    OverrideType,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BloomTaxonomyLevel,
)

RESOLUTION_ENGINE_VERSION = "1.0.0"


class EntityOrigin(StrEnum):
    NATIONAL_BENCHMARK = "national_benchmark"
    INSTITUTIONAL_MODIFIED = "institutional_modified"
    INSTITUTIONAL_CUSTOM = "institutional_custom"


@dataclass(frozen=True, slots=True)
class AppliedOverrideProvenance:
    override_id: str
    override_type: str
    reason: str
    field_overrides: dict[str, Any]
    created_by_email: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EffectiveOutcome:
    id: str
    sequence: int
    description: str
    bloom_level: BloomTaxonomyLevel
    origin: EntityOrigin
    applied_overrides: tuple[AppliedOverrideProvenance, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectiveTopic:
    id: str
    sequence: int
    title: str
    description: str | None
    origin: EntityOrigin
    outcomes: tuple[EffectiveOutcome, ...]
    applied_overrides: tuple[AppliedOverrideProvenance, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectiveCourse:
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    sequence: int
    is_compulsory: bool
    course_category: str
    description: str | None
    origin: EntityOrigin
    topics: tuple[EffectiveTopic, ...]
    applied_overrides: tuple[AppliedOverrideProvenance, ...] = ()
    benchmark_course_id: str | None = None


@dataclass(frozen=True, slots=True)
class OmittedCourse:
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    reason: str
    override_id: str
    created_by_email: str
    benchmark_course_id: str


@dataclass(frozen=True, slots=True)
class EffectiveCurriculumStatistics:
    total_credit_units: int
    total_courses: int
    national_courses_count: int
    modified_courses_count: int
    custom_courses_count: int
    omitted_courses_count: int


@dataclass(frozen=True, slots=True)
class EffectiveCurriculum:
    adoption_id: str
    tenant_id: str
    programme_id: str
    academic_session_id: str | None
    benchmark_curriculum_id: str
    benchmark_version: str
    benchmark_fingerprint: str | None
    effective_curriculum_fingerprint: str
    resolution_engine_version: str
    status: AdoptionStatus
    statistics: EffectiveCurriculumStatistics
    courses: tuple[EffectiveCourse, ...]
    omitted_courses: tuple[OmittedCourse, ...]


class EffectiveCurriculumResolver:
    """Pure domain engine that deterministically resolves Tier 3 Effective Curriculum."""

    def resolve(
        self,
        adoption: InstitutionalAdoption,
        benchmark: BenchmarkCurriculum,
        benchmark_courses: list[BenchmarkCourse],
        overrides: list[CurriculumOverride],
    ) -> EffectiveCurriculum:
        # 1. Verify Benchmark Pinning (Fail Closed)
        if adoption.benchmark_curriculum_id != benchmark.id:
            raise ValueError(
                f"adoption pinned benchmark ID '{adoption.benchmark_curriculum_id}' "
                f"does not match loaded benchmark ID '{benchmark.id}'"
            )
        if adoption.benchmark_version != benchmark.version:
            raise ValueError(
                f"adoption pinned benchmark version '{adoption.benchmark_version}' "
                f"does not match loaded benchmark version '{benchmark.version}'"
            )
        if (
            adoption.benchmark_fingerprint is not None
            and benchmark.review_fingerprint is not None
            and adoption.benchmark_fingerprint != benchmark.review_fingerprint
        ):
            raise ValueError(
                f"adoption pinned benchmark fingerprint '{adoption.benchmark_fingerprint}' "
                f"does not match loaded benchmark review fingerprint '{benchmark.review_fingerprint}'"
            )

        # 2. Group Overrides and Detect Conflicts
        course_overrides_by_code: dict[str, list[CurriculumOverride]] = {}
        custom_courses: list[CurriculumOverride] = []

        for ov in overrides:
            if ov.override_type == OverrideType.ADD_COURSE:
                custom_courses.append(ov)
                continue

            if ov.target_course_code:
                code = ov.target_course_code.upper()
                course_overrides_by_code.setdefault(code, []).append(ov)

        # Conflict Detection: Cannot MODIFY and OMIT the same course
        for code, ov_list in course_overrides_by_code.items():
            types = {o.override_type for o in ov_list}
            if (
                OverrideType.MODIFY_COURSE in types
                and OverrideType.OMIT_COURSE in types
            ):
                raise ValueError(
                    f"conflicting overrides for course '{code}': cannot modify and omit the same course"
                )

            # Detect duplicate field overrides on same course
            seen_fields: set[str] = set()
            for o in ov_list:
                if o.override_type == OverrideType.MODIFY_COURSE and o.field_overrides:
                    for field_name in o.field_overrides:
                        if field_name in seen_fields:
                            raise ValueError(
                                f"duplicate field override '{field_name}' on course '{code}'"
                            )
                        seen_fields.add(field_name)

        # 3. Resolve Benchmark Courses
        resolved_courses: list[EffectiveCourse] = []
        omitted_courses: list[OmittedCourse] = []

        for b_course in benchmark_courses:
            code = b_course.code.upper()
            c_overrides = course_overrides_by_code.get(code, [])

            # Check if omitted
            omissions = [
                o for o in c_overrides if o.override_type == OverrideType.OMIT_COURSE
            ]
            if omissions:
                omit_ov = omissions[0]
                omitted_courses.append(
                    OmittedCourse(
                        code=b_course.code,
                        title=b_course.title,
                        credit_units=b_course.credit_units,
                        level=b_course.level,
                        semester=b_course.semester,
                        reason=omit_ov.reason,
                        override_id=omit_ov.id,
                        created_by_email=omit_ov.created_by_email,
                        benchmark_course_id=b_course.id,
                    )
                )
                continue

            # Process course field modifications
            mod_ovs = [
                o for o in c_overrides if o.override_type == OverrideType.MODIFY_COURSE
            ]
            applied_provs: list[AppliedOverrideProvenance] = []

            title = b_course.title
            credit_units = b_course.credit_units
            level = b_course.level
            semester = b_course.semester
            sequence = b_course.sequence
            is_compulsory = b_course.is_compulsory
            course_category = b_course.course_category
            description = b_course.description
            origin = EntityOrigin.NATIONAL_BENCHMARK

            if mod_ovs:
                origin = EntityOrigin.INSTITUTIONAL_MODIFIED
                for mod_ov in mod_ovs:
                    fields_dict = mod_ov.field_overrides or {}
                    if "title" in fields_dict:
                        title = str(fields_dict["title"])
                    if "credit_units" in fields_dict:
                        credit_units = int(fields_dict["credit_units"])
                    if "level" in fields_dict:
                        level = int(fields_dict["level"])
                    if "semester" in fields_dict:
                        semester = int(fields_dict["semester"])
                    if "sequence" in fields_dict:
                        sequence = int(fields_dict["sequence"])
                    if "is_compulsory" in fields_dict:
                        is_compulsory = bool(fields_dict["is_compulsory"])
                    if "course_category" in fields_dict:
                        course_category = str(fields_dict["course_category"])
                    if "description" in fields_dict:
                        description = str(fields_dict["description"])

                    applied_provs.append(
                        AppliedOverrideProvenance(
                            override_id=mod_ov.id,
                            override_type=mod_ov.override_type.value,
                            reason=mod_ov.reason,
                            field_overrides=fields_dict,
                            created_by_email=mod_ov.created_by_email,
                            created_at=mod_ov.created_at,
                        )
                    )

            # Build Topics and Outcomes
            effective_topics: list[EffectiveTopic] = []
            for b_topic in b_course.topics:
                effective_outcomes: list[EffectiveOutcome] = []
                for b_outcome in b_topic.outcomes:
                    effective_outcomes.append(
                        EffectiveOutcome(
                            id=b_outcome.id,
                            sequence=b_outcome.sequence,
                            description=b_outcome.description,
                            bloom_level=b_outcome.bloom_level
                            or BloomTaxonomyLevel.UNDERSTAND,
                            origin=EntityOrigin.NATIONAL_BENCHMARK,
                        )
                    )
                # Sort outcomes by sequence
                effective_outcomes.sort(key=lambda o: o.sequence)

                effective_topics.append(
                    EffectiveTopic(
                        id=b_topic.id,
                        sequence=b_topic.sequence,
                        title=b_topic.title,
                        description=b_topic.description,
                        origin=EntityOrigin.NATIONAL_BENCHMARK,
                        outcomes=tuple(effective_outcomes),
                    )
                )
            # Sort topics by sequence
            effective_topics.sort(key=lambda t: t.sequence)

            resolved_courses.append(
                EffectiveCourse(
                    code=b_course.code,
                    title=title,
                    credit_units=credit_units,
                    level=level,
                    semester=semester,
                    sequence=sequence,
                    is_compulsory=is_compulsory,
                    course_category=course_category,
                    description=description,
                    origin=origin,
                    topics=tuple(effective_topics),
                    applied_overrides=tuple(applied_provs),
                    benchmark_course_id=b_course.id,
                )
            )

        # 4. Resolve Custom Institutional Courses (ADD_COURSE)
        for custom_ov in custom_courses:
            payload = custom_ov.custom_payload
            raw_code = str(payload.get("code", "")).strip().upper()
            title = str(payload.get("title", ""))
            credit_units = int(payload.get("credit_units", 0))
            level = int(payload.get("level", 100))
            semester = int(payload.get("semester", 1))
            sequence = int(payload.get("sequence", 99))
            is_compulsory = bool(payload.get("is_compulsory", False))
            course_category = str(
                payload.get("course_category", "institutional_custom")
            )
            description = payload.get("description")

            topics_payload = payload.get("topics", [])
            custom_topics: list[EffectiveTopic] = []
            for t_idx, t_data in enumerate(topics_payload, start=1):
                outcomes_payload = t_data.get("outcomes", [])
                custom_outcomes: list[EffectiveOutcome] = []
                for o_idx, o_data in enumerate(outcomes_payload, start=1):
                    bloom_str = str(o_data.get("bloom_level", "understand")).lower()
                    bloom_val = (
                        BloomTaxonomyLevel(bloom_str)
                        if bloom_str in BloomTaxonomyLevel._value2member_map_
                        else BloomTaxonomyLevel.UNDERSTAND
                    )
                    custom_outcomes.append(
                        EffectiveOutcome(
                            id=f"{custom_ov.id}-t{t_idx}-o{o_idx}",
                            sequence=int(o_data.get("sequence", o_idx)),
                            description=str(o_data.get("description", "")),
                            bloom_level=bloom_val,
                            origin=EntityOrigin.INSTITUTIONAL_CUSTOM,
                        )
                    )
                custom_outcomes.sort(key=lambda o: o.sequence)

                custom_topics.append(
                    EffectiveTopic(
                        id=f"{custom_ov.id}-t{t_idx}",
                        sequence=int(t_data.get("sequence", t_idx)),
                        title=str(t_data.get("title", "")),
                        description=t_data.get("description"),
                        origin=EntityOrigin.INSTITUTIONAL_CUSTOM,
                        outcomes=tuple(custom_outcomes),
                    )
                )
            custom_topics.sort(key=lambda t: t.sequence)

            custom_prov = AppliedOverrideProvenance(
                override_id=custom_ov.id,
                override_type=custom_ov.override_type.value,
                reason=custom_ov.reason,
                field_overrides={},
                created_by_email=custom_ov.created_by_email,
                created_at=custom_ov.created_at,
            )

            resolved_courses.append(
                EffectiveCourse(
                    code=raw_code,
                    title=title,
                    credit_units=credit_units,
                    level=level,
                    semester=semester,
                    sequence=sequence,
                    is_compulsory=is_compulsory,
                    course_category=course_category,
                    description=str(description) if description is not None else None,
                    origin=EntityOrigin.INSTITUTIONAL_CUSTOM,
                    topics=tuple(custom_topics),
                    applied_overrides=(custom_prov,),
                    benchmark_course_id=None,
                )
            )

        # 5. Deterministic Ordering of Courses
        # (level ASC, semester ASC, sequence ASC, code ASC)
        resolved_courses.sort(key=lambda c: (c.level, c.semester, c.sequence, c.code))
        omitted_courses.sort(key=lambda c: (c.level, c.semester, c.code))

        # 6. Statistics Calculation
        total_credits = sum(c.credit_units for c in resolved_courses)
        total_courses_count = len(resolved_courses)
        nat_count = sum(
            1 for c in resolved_courses if c.origin == EntityOrigin.NATIONAL_BENCHMARK
        )
        mod_count = sum(
            1
            for c in resolved_courses
            if c.origin == EntityOrigin.INSTITUTIONAL_MODIFIED
        )
        custom_count = sum(
            1 for c in resolved_courses if c.origin == EntityOrigin.INSTITUTIONAL_CUSTOM
        )
        omitted_count = len(omitted_courses)

        stats = EffectiveCurriculumStatistics(
            total_credit_units=total_credits,
            total_courses=total_courses_count,
            national_courses_count=nat_count,
            modified_courses_count=mod_count,
            custom_courses_count=custom_count,
            omitted_courses_count=omitted_count,
        )

        # 7. Compute Effective Curriculum Fingerprint
        canonical_projection = {
            "engine_version": RESOLUTION_ENGINE_VERSION,
            "adoption_id": adoption.id,
            "tenant_id": adoption.tenant_id,
            "programme_id": adoption.programme_id,
            "benchmark_curriculum_id": benchmark.id,
            "benchmark_version": benchmark.version,
            "benchmark_fingerprint": adoption.benchmark_fingerprint
            or benchmark.review_fingerprint
            or "",
            "courses": [
                {
                    "code": c.code,
                    "title": c.title,
                    "credit_units": c.credit_units,
                    "level": c.level,
                    "semester": c.semester,
                    "sequence": c.sequence,
                    "is_compulsory": c.is_compulsory,
                    "course_category": c.course_category,
                    "origin": c.origin.value,
                    "overrides": [
                        {"id": p.override_id, "type": p.override_type}
                        for p in c.applied_overrides
                    ],
                    "topics": [
                        {
                            "sequence": t.sequence,
                            "title": t.title,
                            "outcomes": [
                                {"sequence": o.sequence, "bloom": o.bloom_level.value}
                                for o in t.outcomes
                            ],
                        }
                        for t in c.topics
                    ],
                }
                for c in resolved_courses
            ],
            "omitted_courses": [
                {"code": o.code, "override_id": o.override_id} for o in omitted_courses
            ],
        }
        canonical_json = json.dumps(
            canonical_projection, sort_keys=True, separators=(",", ":")
        )
        eff_fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        return EffectiveCurriculum(
            adoption_id=adoption.id,
            tenant_id=adoption.tenant_id,
            programme_id=adoption.programme_id,
            academic_session_id=adoption.academic_session_id,
            benchmark_curriculum_id=adoption.benchmark_curriculum_id,
            benchmark_version=adoption.benchmark_version,
            benchmark_fingerprint=adoption.benchmark_fingerprint,
            effective_curriculum_fingerprint=eff_fingerprint,
            resolution_engine_version=RESOLUTION_ENGINE_VERSION,
            status=adoption.status,
            statistics=stats,
            courses=tuple(resolved_courses),
            omitted_courses=tuple(omitted_courses),
        )
