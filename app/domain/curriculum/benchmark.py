from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from app.events.base import DomainEvent


class BenchmarkStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class BloomTaxonomyLevel(StrEnum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


@dataclass
class BenchmarkOutcome:
    id: str
    benchmark_topic_id: str
    sequence: int
    description: str
    bloom_level: BloomTaxonomyLevel | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        benchmark_topic_id: str,
        sequence: int,
        description: str,
        bloom_level: BloomTaxonomyLevel | None = None,
        outcome_id: str | None = None,
    ) -> BenchmarkOutcome:
        if not description.strip():
            raise ValueError("outcome description cannot be empty")
        if sequence < 1:
            raise ValueError("outcome sequence must be at least 1")

        return cls(
            id=outcome_id or str(uuid4()),
            benchmark_topic_id=benchmark_topic_id,
            sequence=sequence,
            description=description.strip(),
            bloom_level=bloom_level,
        )


@dataclass
class BenchmarkTopic:
    id: str
    benchmark_course_id: str
    sequence: int
    title: str
    description: str | None = None
    outcomes: list[BenchmarkOutcome] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        benchmark_course_id: str,
        sequence: int,
        title: str,
        description: str | None = None,
        outcomes: list[BenchmarkOutcome] | None = None,
        topic_id: str | None = None,
    ) -> BenchmarkTopic:
        if not title.strip():
            raise ValueError("topic title cannot be empty")
        if sequence < 1:
            raise ValueError("topic sequence must be at least 1")

        return cls(
            id=topic_id or str(uuid4()),
            benchmark_course_id=benchmark_course_id,
            sequence=sequence,
            title=title.strip(),
            description=description.strip() if description else None,
            outcomes=outcomes or [],
        )

    def add_outcome(self, outcome: BenchmarkOutcome) -> None:
        if any(o.sequence == outcome.sequence for o in self.outcomes):
            raise ValueError(f"outcome with sequence {outcome.sequence} already exists in topic")
        self.outcomes.append(outcome)


@dataclass
class BenchmarkCourse:
    id: str
    benchmark_curriculum_id: str
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    is_compulsory: bool = True
    course_category: str = "core"
    description: str | None = None
    sequence: int = 1
    topics: list[BenchmarkTopic] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        benchmark_curriculum_id: str,
        code: str,
        title: str,
        credit_units: int,
        level: int,
        semester: int,
        is_compulsory: bool = True,
        course_category: str = "core",
        description: str | None = None,
        sequence: int = 1,
        topics: list[BenchmarkTopic] | None = None,
        course_id: str | None = None,
    ) -> BenchmarkCourse:
        clean_code = code.strip().replace(" ", "").upper()
        if not clean_code:
            raise ValueError("course code cannot be empty")
        if not title.strip():
            raise ValueError("course title cannot be empty")
        if credit_units < 1 or credit_units > 12:
            raise ValueError("credit_units must be between 1 and 12")
        if level not in (100, 200, 300, 400, 500, 600):
            raise ValueError("level must be one of [100, 200, 300, 400, 500, 600]")
        if semester not in (1, 2):
            raise ValueError("semester must be 1 or 2")
        if sequence < 1:
            raise ValueError("course sequence must be at least 1")

        return cls(
            id=course_id or str(uuid4()),
            benchmark_curriculum_id=benchmark_curriculum_id,
            code=clean_code,
            title=title.strip(),
            credit_units=credit_units,
            level=level,
            semester=semester,
            is_compulsory=is_compulsory,
            course_category=course_category.strip(),
            description=description.strip() if description else None,
            sequence=sequence,
            topics=topics or [],
        )

    def add_topic(self, topic: BenchmarkTopic) -> None:
        if any(t.sequence == topic.sequence for t in self.topics):
            raise ValueError(f"topic with sequence {topic.sequence} already exists in course {self.code}")
        self.topics.append(topic)


@dataclass
class BenchmarkCurriculum:
    id: str
    source_snapshot_id: str
    discipline_group: str
    programme_name: str
    programme_code: str
    version: str
    degree_level: str = "undergraduate"
    minimum_credit_units: int = 120
    status: BenchmarkStatus = BenchmarkStatus.CANDIDATE
    review_fingerprint: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create_candidate(
        cls,
        source_snapshot_id: str,
        discipline_group: str,
        programme_name: str,
        programme_code: str,
        version: str,
        degree_level: str = "undergraduate",
        minimum_credit_units: int = 120,
        curriculum_id: str | None = None,
        review_fingerprint: str | None = None,
    ) -> BenchmarkCurriculum:
        if not source_snapshot_id.strip():
            raise ValueError("source_snapshot_id cannot be empty")
        if not discipline_group.strip():
            raise ValueError("discipline_group cannot be empty")
        if not programme_name.strip():
            raise ValueError("programme_name cannot be empty")
        clean_prog_code = programme_code.strip().upper()
        if not clean_prog_code:
            raise ValueError("programme_code cannot be empty")
        if not version.strip():
            raise ValueError("version cannot be empty")
        if minimum_credit_units < 1:
            raise ValueError("minimum_credit_units must be at least 1")

        now = datetime.now(timezone.utc)
        curriculum = cls(
            id=curriculum_id or str(uuid4()),
            source_snapshot_id=source_snapshot_id.strip(),
            discipline_group=discipline_group.strip(),
            programme_name=programme_name.strip(),
            programme_code=clean_prog_code,
            version=version.strip(),
            degree_level=degree_level.strip(),
            minimum_credit_units=minimum_credit_units,
            status=BenchmarkStatus.CANDIDATE,
            review_fingerprint=review_fingerprint,
            created_at=now,
            updated_at=now,
        )
        curriculum._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_candidate_created",
                payload={
                    "curriculum_id": curriculum.id,
                    "source_snapshot_id": curriculum.source_snapshot_id,
                    "programme_code": curriculum.programme_code,
                    "version": curriculum.version,
                },
            )
        )
        return curriculum

    def is_mutable(self) -> bool:
        return self.status == BenchmarkStatus.CANDIDATE

    def mark_validated(self) -> None:
        if self.status != BenchmarkStatus.CANDIDATE:
            raise ValueError(f"only candidate benchmarks can be validated, current status is '{self.status.value}'")
        self.status = BenchmarkStatus.VALIDATED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_validated",
                payload={
                    "curriculum_id": self.id,
                    "source_snapshot_id": self.source_snapshot_id,
                    "discipline_group": self.discipline_group,
                    "programme_code": self.programme_code,
                    "degree_level": self.degree_level,
                    "version": self.version,
                },
            )
        )

    def submit_for_review(
        self,
        diff_fingerprint: str | None = None,
        notes: str | None = None,
    ) -> None:
        if self.status != BenchmarkStatus.VALIDATED:
            raise ValueError(f"only validated benchmarks can be submitted for review, current status is '{self.status.value}'")
        self.status = BenchmarkStatus.UNDER_REVIEW
        self.review_fingerprint = diff_fingerprint
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_submitted_for_review",
                payload={
                    "curriculum_id": self.id,
                    "source_snapshot_id": self.source_snapshot_id,
                    "discipline_group": self.discipline_group,
                    "programme_code": self.programme_code,
                    "degree_level": self.degree_level,
                    "version": self.version,
                    "diff_fingerprint": diff_fingerprint,
                    "notes": notes,
                },
            )
        )

    def approve(self, reviewer_id: str, reason: str) -> None:
        if self.status != BenchmarkStatus.UNDER_REVIEW:
            raise ValueError(f"only benchmarks under review can be approved, current status is '{self.status.value}'")
        if not reason.strip():
            raise ValueError("approval reason cannot be empty")
        self.status = BenchmarkStatus.APPROVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_approved",
                payload={
                    "curriculum_id": self.id,
                    "source_snapshot_id": self.source_snapshot_id,
                    "discipline_group": self.discipline_group,
                    "programme_code": self.programme_code,
                    "degree_level": self.degree_level,
                    "version": self.version,
                    "reviewer_id": reviewer_id,
                    "reason": reason.strip(),
                    "diff_fingerprint": self.review_fingerprint,
                },
            )
        )

    def reject(self, reviewer_id: str, reason: str) -> None:
        if self.status != BenchmarkStatus.UNDER_REVIEW:
            raise ValueError(f"only benchmarks under review can be rejected, current status is '{self.status.value}'")
        if not reason.strip():
            raise ValueError("rejection reason cannot be empty")
        self.status = BenchmarkStatus.REJECTED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_rejected",
                payload={
                    "curriculum_id": self.id,
                    "source_snapshot_id": self.source_snapshot_id,
                    "discipline_group": self.discipline_group,
                    "programme_code": self.programme_code,
                    "degree_level": self.degree_level,
                    "version": self.version,
                    "reviewer_id": reviewer_id,
                    "reason": reason.strip(),
                },
            )
        )

    def revise_to_candidate(self) -> None:
        if self.status != BenchmarkStatus.REJECTED:
            raise ValueError(f"only rejected benchmarks can be revised to candidate, current status is '{self.status.value}'")
        self.status = BenchmarkStatus.CANDIDATE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_revised_to_candidate",
                payload={
                    "curriculum_id": self.id,
                    "source_snapshot_id": self.source_snapshot_id,
                    "discipline_group": self.discipline_group,
                    "programme_code": self.programme_code,
                    "degree_level": self.degree_level,
                    "version": self.version,
                },
            )
        )

    def activate(
        self,
        superseded_id: str | None = None,
        activated_by: str | None = None,
    ) -> None:
        if self.status != BenchmarkStatus.APPROVED:
            raise ValueError(f"only approved benchmarks can be activated, current status is '{self.status.value}'")
        self.status = BenchmarkStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_activated",
                payload={
                    "curriculum_id": self.id,
                    "source_snapshot_id": self.source_snapshot_id,
                    "discipline_group": self.discipline_group,
                    "programme_code": self.programme_code,
                    "degree_level": self.degree_level,
                    "version": self.version,
                    "superseded_id": superseded_id,
                    "activated_by": activated_by,
                    "diff_fingerprint": self.review_fingerprint,
                },
            )
        )

    def supersede(self) -> None:
        if self.status != BenchmarkStatus.ACTIVE:
            raise ValueError(f"only active benchmarks can be superseded, current status is '{self.status.value}'")
        self.status = BenchmarkStatus.SUPERSEDED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum.benchmark_superseded",
                payload={
                    "curriculum_id": self.id,
                    "source_snapshot_id": self.source_snapshot_id,
                    "discipline_group": self.discipline_group,
                    "programme_code": self.programme_code,
                    "degree_level": self.degree_level,
                    "version": self.version,
                },
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
