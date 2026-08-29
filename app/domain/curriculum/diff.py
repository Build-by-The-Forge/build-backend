from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkTopic,
)


class DiffAction(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass(slots=True)
class FieldDiff:
    field: str
    old_value: Any
    new_value: Any


@dataclass(slots=True)
class OutcomeDiff:
    sequence: int
    action: DiffAction
    description: str
    field_diffs: list[FieldDiff] = field(default_factory=list)


@dataclass(slots=True)
class TopicDiff:
    sequence: int
    title: str
    action: DiffAction
    field_diffs: list[FieldDiff] = field(default_factory=list)
    outcome_diffs: list[OutcomeDiff] = field(default_factory=list)


@dataclass(slots=True)
class CourseDiff:
    code: str
    title: str
    action: DiffAction
    field_diffs: list[FieldDiff] = field(default_factory=list)
    topic_diffs: list[TopicDiff] = field(default_factory=list)


@dataclass(slots=True)
class DiffStatistics:
    courses_added: int = 0
    courses_removed: int = 0
    courses_modified: int = 0
    topics_added: int = 0
    topics_removed: int = 0
    topics_modified: int = 0
    outcomes_added: int = 0
    outcomes_removed: int = 0
    outcomes_modified: int = 0
    credit_units_before: int = 0
    credit_units_after: int = 0
    credit_units_delta: int = 0


@dataclass(slots=True)
class BenchmarkCurriculumDiff:
    source_curriculum_id: str
    target_curriculum_id: str
    source_version: str
    target_version: str
    discipline_group: str
    programme_code: str
    degree_level: str
    diff_fingerprint: str
    statistics: DiffStatistics
    course_diffs: list[CourseDiff] = field(default_factory=list)


class BenchmarkCurriculumDiffEngine:
    """Pure domain, deterministic comparison engine between two benchmark versions.

    Calculates exact hierarchical structural mutations across:
    Curriculum -> Course -> Topic -> Learning Outcome.
    """

    def compare(
        self,
        source_curriculum: BenchmarkCurriculum,
        source_courses: list[BenchmarkCourse],
        target_curriculum: BenchmarkCurriculum,
        target_courses: list[BenchmarkCourse],
    ) -> BenchmarkCurriculumDiff:
        # Build maps by normalized course code
        source_map = {c.code.upper(): c for c in source_courses}
        target_map = {c.code.upper(): c for c in target_courses}

        all_codes = sorted(set(source_map.keys()) | set(target_map.keys()))

        course_diffs: list[CourseDiff] = []
        stats = DiffStatistics()

        stats.credit_units_before = sum(c.credit_units for c in source_courses)
        stats.credit_units_after = sum(c.credit_units for c in target_courses)
        stats.credit_units_delta = stats.credit_units_after - stats.credit_units_before

        for code in all_codes:
            if code not in source_map:
                # Course ADDED in target
                target_course = target_map[code]
                stats.courses_added += 1
                topic_diffs = []
                for t in sorted(target_course.topics, key=lambda x: x.sequence):
                    stats.topics_added += 1
                    outcome_diffs = []
                    for o in sorted(t.outcomes, key=lambda x: x.sequence):
                        stats.outcomes_added += 1
                        outcome_diffs.append(
                            OutcomeDiff(
                                sequence=o.sequence,
                                action=DiffAction.ADDED,
                                description=o.description,
                            )
                        )
                    topic_diffs.append(
                        TopicDiff(
                            sequence=t.sequence,
                            title=t.title,
                            action=DiffAction.ADDED,
                            outcome_diffs=outcome_diffs,
                        )
                    )
                course_diffs.append(
                    CourseDiff(
                        code=code,
                        title=target_course.title,
                        action=DiffAction.ADDED,
                        topic_diffs=topic_diffs,
                    )
                )

            elif code not in target_map:
                # Course REMOVED in target
                source_course = source_map[code]
                stats.courses_removed += 1
                topic_diffs = []
                for t in sorted(source_course.topics, key=lambda x: x.sequence):
                    stats.topics_removed += 1
                    outcome_diffs = []
                    for o in sorted(t.outcomes, key=lambda x: x.sequence):
                        stats.outcomes_removed += 1
                        outcome_diffs.append(
                            OutcomeDiff(
                                sequence=o.sequence,
                                action=DiffAction.REMOVED,
                                description=o.description,
                            )
                        )
                    topic_diffs.append(
                        TopicDiff(
                            sequence=t.sequence,
                            title=t.title,
                            action=DiffAction.REMOVED,
                            outcome_diffs=outcome_diffs,
                        )
                    )
                course_diffs.append(
                    CourseDiff(
                        code=code,
                        title=source_course.title,
                        action=DiffAction.REMOVED,
                        topic_diffs=topic_diffs,
                    )
                )

            else:
                # Course in both -> check mutations
                source_course = source_map[code]
                target_course = target_map[code]
                c_diff = self._compare_courses(source_course, target_course, stats)
                if c_diff is not None:
                    stats.courses_modified += 1
                    course_diffs.append(c_diff)

        # Compute deterministic diff fingerprint
        fingerprint = self._compute_fingerprint(
            source_curriculum=source_curriculum,
            target_curriculum=target_curriculum,
            stats=stats,
            course_diffs=course_diffs,
        )

        return BenchmarkCurriculumDiff(
            source_curriculum_id=source_curriculum.id,
            target_curriculum_id=target_curriculum.id,
            source_version=source_curriculum.version,
            target_version=target_curriculum.version,
            discipline_group=source_curriculum.discipline_group,
            programme_code=source_curriculum.programme_code,
            degree_level=source_curriculum.degree_level,
            diff_fingerprint=fingerprint,
            statistics=stats,
            course_diffs=course_diffs,
        )

    def _compare_courses(
        self,
        source: BenchmarkCourse,
        target: BenchmarkCourse,
        stats: DiffStatistics,
    ) -> CourseDiff | None:
        field_diffs: list[FieldDiff] = []

        if source.title != target.title:
            field_diffs.append(FieldDiff("title", source.title, target.title))
        if source.credit_units != target.credit_units:
            field_diffs.append(
                FieldDiff("credit_units", source.credit_units, target.credit_units)
            )
        if source.level != target.level:
            field_diffs.append(FieldDiff("level", source.level, target.level))
        if source.semester != target.semester:
            field_diffs.append(FieldDiff("semester", source.semester, target.semester))
        if source.is_compulsory != target.is_compulsory:
            field_diffs.append(
                FieldDiff("is_compulsory", source.is_compulsory, target.is_compulsory)
            )
        if source.course_category != target.course_category:
            field_diffs.append(
                FieldDiff(
                    "course_category",
                    source.course_category,
                    target.course_category,
                )
            )
        if source.sequence != target.sequence:
            field_diffs.append(FieldDiff("sequence", source.sequence, target.sequence))
        if source.description != target.description:
            field_diffs.append(
                FieldDiff("description", source.description, target.description)
            )

        # Sort field diffs deterministically
        field_diffs.sort(key=lambda f: f.field)

        # Compare topics
        topic_diffs = self._compare_topics(source.topics, target.topics, stats)

        if not field_diffs and not topic_diffs:
            return None

        return CourseDiff(
            code=target.code,
            title=target.title,
            action=DiffAction.MODIFIED,
            field_diffs=field_diffs,
            topic_diffs=topic_diffs,
        )

    def _compare_topics(
        self,
        source_topics: list[BenchmarkTopic],
        target_topics: list[BenchmarkTopic],
        stats: DiffStatistics,
    ) -> list[TopicDiff]:
        source_by_seq = {t.sequence: t for t in source_topics}
        target_by_seq = {t.sequence: t for t in target_topics}

        all_seqs = sorted(set(source_by_seq.keys()) | set(target_by_seq.keys()))
        topic_diffs: list[TopicDiff] = []

        for seq in all_seqs:
            if seq not in source_by_seq:
                target_t = target_by_seq[seq]
                stats.topics_added += 1
                o_diffs = []
                for o in sorted(target_t.outcomes, key=lambda x: x.sequence):
                    stats.outcomes_added += 1
                    o_diffs.append(
                        OutcomeDiff(
                            sequence=o.sequence,
                            action=DiffAction.ADDED,
                            description=o.description,
                        )
                    )
                topic_diffs.append(
                    TopicDiff(
                        sequence=seq,
                        title=target_t.title,
                        action=DiffAction.ADDED,
                        outcome_diffs=o_diffs,
                    )
                )

            elif seq not in target_by_seq:
                source_t = source_by_seq[seq]
                stats.topics_removed += 1
                o_diffs = []
                for o in sorted(source_t.outcomes, key=lambda x: x.sequence):
                    stats.outcomes_removed += 1
                    o_diffs.append(
                        OutcomeDiff(
                            sequence=o.sequence,
                            action=DiffAction.REMOVED,
                            description=o.description,
                        )
                    )
                topic_diffs.append(
                    TopicDiff(
                        sequence=seq,
                        title=source_t.title,
                        action=DiffAction.REMOVED,
                        outcome_diffs=o_diffs,
                    )
                )

            else:
                source_t = source_by_seq[seq]
                target_t = target_by_seq[seq]
                t_diff = self._compare_single_topic(source_t, target_t, stats)
                if t_diff is not None:
                    stats.topics_modified += 1
                    topic_diffs.append(t_diff)

        topic_diffs.sort(key=lambda t: t.sequence)
        return topic_diffs

    def _compare_single_topic(
        self,
        source: BenchmarkTopic,
        target: BenchmarkTopic,
        stats: DiffStatistics,
    ) -> TopicDiff | None:
        field_diffs: list[FieldDiff] = []
        if source.title != target.title:
            field_diffs.append(FieldDiff("title", source.title, target.title))
        if source.description != target.description:
            field_diffs.append(
                FieldDiff("description", source.description, target.description)
            )
        field_diffs.sort(key=lambda f: f.field)

        outcome_diffs = self._compare_outcomes(source.outcomes, target.outcomes, stats)

        if not field_diffs and not outcome_diffs:
            return None

        return TopicDiff(
            sequence=target.sequence,
            title=target.title,
            action=DiffAction.MODIFIED,
            field_diffs=field_diffs,
            outcome_diffs=outcome_diffs,
        )

    def _compare_outcomes(
        self,
        source_outcomes: list[BenchmarkOutcome],
        target_outcomes: list[BenchmarkOutcome],
        stats: DiffStatistics,
    ) -> list[OutcomeDiff]:
        source_by_seq = {o.sequence: o for o in source_outcomes}
        target_by_seq = {o.sequence: o for o in target_outcomes}

        all_seqs = sorted(set(source_by_seq.keys()) | set(target_by_seq.keys()))
        outcome_diffs: list[OutcomeDiff] = []

        for seq in all_seqs:
            if seq not in source_by_seq:
                target_o = target_by_seq[seq]
                stats.outcomes_added += 1
                outcome_diffs.append(
                    OutcomeDiff(
                        sequence=seq,
                        action=DiffAction.ADDED,
                        description=target_o.description,
                    )
                )
            elif seq not in target_by_seq:
                source_o = source_by_seq[seq]
                stats.outcomes_removed += 1
                outcome_diffs.append(
                    OutcomeDiff(
                        sequence=seq,
                        action=DiffAction.REMOVED,
                        description=source_o.description,
                    )
                )
            else:
                source_o = source_by_seq[seq]
                target_o = target_by_seq[seq]
                o_diff = self._compare_single_outcome(source_o, target_o)
                if o_diff is not None:
                    stats.outcomes_modified += 1
                    outcome_diffs.append(o_diff)

        outcome_diffs.sort(key=lambda o: o.sequence)
        return outcome_diffs

    def _compare_single_outcome(
        self,
        source: BenchmarkOutcome,
        target: BenchmarkOutcome,
    ) -> OutcomeDiff | None:
        field_diffs: list[FieldDiff] = []
        if source.description != target.description:
            field_diffs.append(
                FieldDiff("description", source.description, target.description)
            )
        if source.bloom_level != target.bloom_level:
            field_diffs.append(
                FieldDiff(
                    "bloom_level",
                    source.bloom_level.value if source.bloom_level else None,
                    target.bloom_level.value if target.bloom_level else None,
                )
            )
        field_diffs.sort(key=lambda f: f.field)

        if not field_diffs:
            return None

        return OutcomeDiff(
            sequence=target.sequence,
            action=DiffAction.MODIFIED,
            description=target.description,
            field_diffs=field_diffs,
        )

    def _compute_fingerprint(
        self,
        source_curriculum: BenchmarkCurriculum,
        target_curriculum: BenchmarkCurriculum,
        stats: DiffStatistics,
        course_diffs: list[CourseDiff],
    ) -> str:
        serialized = {
            "source_id": source_curriculum.id,
            "target_id": target_curriculum.id,
            "source_version": source_curriculum.version,
            "target_version": target_curriculum.version,
            "stats": {
                "courses_added": stats.courses_added,
                "courses_removed": stats.courses_removed,
                "courses_modified": stats.courses_modified,
                "topics_added": stats.topics_added,
                "topics_removed": stats.topics_removed,
                "topics_modified": stats.topics_modified,
                "outcomes_added": stats.outcomes_added,
                "outcomes_removed": stats.outcomes_removed,
                "outcomes_modified": stats.outcomes_modified,
                "credit_delta": stats.credit_units_delta,
            },
            "diffs": [
                {
                    "code": c.code,
                    "action": c.action.value,
                    "fields": [
                        {"field": f.field, "old": f.old_value, "new": f.new_value}
                        for f in c.field_diffs
                    ],
                }
                for c in course_diffs
            ],
        }
        raw_bytes = json.dumps(serialized, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()
