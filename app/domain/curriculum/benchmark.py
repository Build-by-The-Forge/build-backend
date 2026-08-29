from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from app.events.base import DomainEvent


class BenchmarkStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
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
            id=outcome_id or f"outcome-{uuid4()}",
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
            id=topic_id or f"topic-{uuid4()}",
            benchmark_course_id=benchmark_course_id,
            sequence=sequence,
            title=title.strip(),
            description=description.strip() if description else None,
            outcomes=outcomes or [],
        )

    def add_outcome(self, outcome: BenchmarkOutcome) -> None:
        if any(o.sequence == outcome.sequence for o in self.outcomes):
            raise ValueError(
                f"outcome with sequence {outcome.sequence} already exists in topic"
            )
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
            id=course_id or f"bmcourse-{uuid4()}",
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
            raise ValueError(
                f"topic with sequence {topic.sequence} already exists in course {self.code}"
            )
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
            id=curriculum_id or f"bmcurr-{uuid4()}",
            source_snapshot_id=source_snapshot_id.strip(),
            discipline_group=discipline_group.strip(),
            programme_name=programme_name.strip(),
            programme_code=clean_prog_code,
            version=version.strip(),
            degree_level=degree_level.strip(),
            minimum_credit_units=minimum_credit_units,
            status=BenchmarkStatus.CANDIDATE,
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

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
