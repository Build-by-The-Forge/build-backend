from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BloomTaxonomyLevel,
)


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(slots=True)
class ValidationIssue:
    entity_type: str
    entity_identifier: str
    field: str
    rule: str
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR


@dataclass(slots=True)
class ValidationResult:
    is_valid: bool
    error_count: int
    warning_count: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @classmethod
    def from_issues(cls, issues: list[ValidationIssue]) -> ValidationResult:
        error_count = sum(
            1 for issue in issues if issue.severity == IssueSeverity.ERROR
        )
        warning_count = sum(
            1 for issue in issues if issue.severity == IssueSeverity.WARNING
        )
        return cls(
            is_valid=(error_count == 0),
            error_count=error_count,
            warning_count=warning_count,
            issues=issues,
        )


class BenchmarkCurriculumValidator:
    """Pure domain validation engine for national benchmark curriculum candidates.

    Enforces:
    1. Hard Structural Invariants (code uniqueness, monotonic sequences, non-empty trees).
    2. Source-Derived Academic Rules (credit threshold sanity based on source metadata).
    """

    def validate(
        self,
        curriculum: BenchmarkCurriculum,
        courses: list[BenchmarkCourse],
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []

        # =========================================================================
        # 1. CURRICULUM LEVEL INVARIANTS
        # =========================================================================
        if not curriculum.programme_code.strip():
            issues.append(
                ValidationIssue(
                    entity_type="Curriculum",
                    entity_identifier=curriculum.id,
                    field="programme_code",
                    rule="REQUIRED_FIELD",
                    message="Curriculum programme_code cannot be blank.",
                    severity=IssueSeverity.ERROR,
                )
            )

        if not curriculum.programme_name.strip():
            issues.append(
                ValidationIssue(
                    entity_type="Curriculum",
                    entity_identifier=curriculum.id,
                    field="programme_name",
                    rule="REQUIRED_FIELD",
                    message="Curriculum programme_name cannot be blank.",
                    severity=IssueSeverity.ERROR,
                )
            )

        if not curriculum.version.strip():
            issues.append(
                ValidationIssue(
                    entity_type="Curriculum",
                    entity_identifier=curriculum.id,
                    field="version",
                    rule="REQUIRED_FIELD",
                    message="Curriculum version cannot be blank.",
                    severity=IssueSeverity.ERROR,
                )
            )

        if not courses:
            issues.append(
                ValidationIssue(
                    entity_type="Curriculum",
                    entity_identifier=curriculum.id,
                    field="courses",
                    rule="NON_EMPTY_COURSES",
                    message="Benchmark candidate must contain at least one course.",
                    severity=IssueSeverity.ERROR,
                )
            )
            return ValidationResult.from_issues(issues)

        # Source-derived minimum credit unit check
        total_credit_units = sum(c.credit_units for c in courses)
        if (
            curriculum.minimum_credit_units > 0
            and total_credit_units < curriculum.minimum_credit_units
        ):
            issues.append(
                ValidationIssue(
                    entity_type="Curriculum",
                    entity_identifier=curriculum.id,
                    field="minimum_credit_units",
                    rule="MINIMUM_CREDIT_UNITS",
                    message=(
                        f"Total credit units ({total_credit_units}) is less than the "
                        f"minimum credit units threshold ({curriculum.minimum_credit_units}) specified in source metadata."
                    ),
                    severity=IssueSeverity.WARNING,
                )
            )

        # =========================================================================
        # 2. COURSE LEVEL INVARIANTS
        # =========================================================================
        seen_course_codes: set[str] = set()
        seen_course_sequences: set[int] = set()

        for course in sorted(courses, key=lambda c: c.sequence):
            # Code format & uniqueness
            clean_code = course.code.strip().replace(" ", "").upper()
            if not clean_code:
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.id,
                        field="code",
                        rule="REQUIRED_FIELD",
                        message="Course code cannot be blank.",
                        severity=IssueSeverity.ERROR,
                    )
                )
            elif clean_code in seen_course_codes:
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.id,
                        field="code",
                        rule="UNIQUE_COURSE_CODE",
                        message=f"Duplicate course code '{clean_code}' detected in curriculum.",
                        severity=IssueSeverity.ERROR,
                    )
                )
            else:
                seen_course_codes.add(clean_code)

            # Course sequence uniqueness
            if course.sequence in seen_course_sequences:
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.id,
                        field="sequence",
                        rule="UNIQUE_COURSE_SEQUENCE",
                        message=f"Duplicate course sequence '{course.sequence}' for course '{course.code}'.",
                        severity=IssueSeverity.ERROR,
                    )
                )
            else:
                seen_course_sequences.add(course.sequence)

            # Credit units range
            if course.credit_units < 1 or course.credit_units > 12:
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.code,
                        field="credit_units",
                        rule="CREDIT_UNITS_RANGE",
                        message=f"Course '{course.code}' credit units ({course.credit_units}) must be between 1 and 12.",
                        severity=IssueSeverity.ERROR,
                    )
                )

            # Level validation
            if course.level not in (100, 200, 300, 400, 500, 600):
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.code,
                        field="level",
                        rule="ACADEMIC_LEVEL_RANGE",
                        message=f"Course '{course.code}' level ({course.level}) must be one of [100, 200, 300, 400, 500, 600].",
                        severity=IssueSeverity.ERROR,
                    )
                )

            # Semester validation
            if course.semester not in (1, 2):
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.code,
                        field="semester",
                        rule="SEMESTER_RANGE",
                        message=f"Course '{course.code}' semester ({course.semester}) must be 1 or 2.",
                        severity=IssueSeverity.ERROR,
                    )
                )

            # Title validation
            if not course.title.strip():
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.code,
                        field="title",
                        rule="REQUIRED_FIELD",
                        message=f"Course '{course.code}' title cannot be blank.",
                        severity=IssueSeverity.ERROR,
                    )
                )

            # Topics non-empty check
            if not course.topics:
                issues.append(
                    ValidationIssue(
                        entity_type="Course",
                        entity_identifier=course.code,
                        field="topics",
                        rule="NON_EMPTY_TOPICS",
                        message=f"Course '{course.code}' must contain at least one topic.",
                        severity=IssueSeverity.ERROR,
                    )
                )
                continue

            # =====================================================================
            # 3. TOPIC LEVEL INVARIANTS
            # =====================================================================
            sorted_topics = sorted(course.topics, key=lambda t: t.sequence)
            expected_topic_seq = 1

            for topic in sorted_topics:
                if topic.sequence != expected_topic_seq:
                    issues.append(
                        ValidationIssue(
                            entity_type="Topic",
                            entity_identifier=f"{course.code}:Topic-{topic.sequence}",
                            field="sequence",
                            rule="MONOTONIC_SEQUENCE",
                            message=(
                                f"Topic in course '{course.code}' has sequence {topic.sequence}, "
                                f"expected sequential sequence {expected_topic_seq}."
                            ),
                            severity=IssueSeverity.ERROR,
                        )
                    )
                expected_topic_seq += 1

                if not topic.title.strip():
                    issues.append(
                        ValidationIssue(
                            entity_type="Topic",
                            entity_identifier=f"{course.code}:Topic-{topic.sequence}",
                            field="title",
                            rule="REQUIRED_FIELD",
                            message=f"Topic {topic.sequence} in course '{course.code}' title cannot be blank.",
                            severity=IssueSeverity.ERROR,
                        )
                    )

                if not topic.outcomes:
                    issues.append(
                        ValidationIssue(
                            entity_type="Topic",
                            entity_identifier=f"{course.code}:Topic-{topic.sequence}",
                            field="outcomes",
                            rule="NON_EMPTY_OUTCOMES",
                            message=(
                                f"Topic '{topic.title}' in course '{course.code}' "
                                "must contain at least one learning outcome."
                            ),
                            severity=IssueSeverity.ERROR,
                        )
                    )
                    continue

                # =================================================================
                # 4. OUTCOME LEVEL INVARIANTS
                # =================================================================
                sorted_outcomes = sorted(topic.outcomes, key=lambda o: o.sequence)
                expected_outcome_seq = 1

                for outcome in sorted_outcomes:
                    if outcome.sequence != expected_outcome_seq:
                        issues.append(
                            ValidationIssue(
                                entity_type="Outcome",
                                entity_identifier=f"{course.code}:Topic-{topic.sequence}:Outcome-{outcome.sequence}",
                                field="sequence",
                                rule="MONOTONIC_SEQUENCE",
                                message=(
                                    f"Outcome in topic '{topic.title}' has sequence {outcome.sequence}, "
                                    f"expected sequential sequence {expected_outcome_seq}."
                                ),
                                severity=IssueSeverity.ERROR,
                            )
                        )
                    expected_outcome_seq += 1

                    if (
                        not outcome.description.strip()
                        or len(outcome.description.strip()) < 5
                    ):
                        issues.append(
                            ValidationIssue(
                                entity_type="Outcome",
                                entity_identifier=f"{course.code}:Topic-{topic.sequence}:Outcome-{outcome.sequence}",
                                field="description",
                                rule="DESCRIPTION_LENGTH",
                                message=(
                                    f"Outcome {outcome.sequence} in topic '{topic.title}' "
                                    "description must be at least 5 characters long."
                                ),
                                severity=IssueSeverity.ERROR,
                            )
                        )

                    if outcome.bloom_level is not None:
                        if not isinstance(outcome.bloom_level, BloomTaxonomyLevel):
                            issues.append(
                                ValidationIssue(
                                    entity_type="Outcome",
                                    entity_identifier=f"{course.code}:Topic-{topic.sequence}:Outcome-{outcome.sequence}",
                                    field="bloom_level",
                                    rule="BLOOM_TAXONOMY_VALID",
                                    message=(
                                        f"Outcome {outcome.sequence} in topic '{topic.title}' "
                                        f"has invalid Bloom taxonomy level '{outcome.bloom_level}'."
                                    ),
                                    severity=IssueSeverity.ERROR,
                                )
                            )

        return ValidationResult.from_issues(issues)
