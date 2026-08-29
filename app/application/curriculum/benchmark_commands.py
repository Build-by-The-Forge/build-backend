from dataclasses import dataclass, field


@dataclass(slots=True)
class BenchmarkOutcomeInput:
    sequence: int
    description: str
    bloom_level: str | None = None


@dataclass(slots=True)
class BenchmarkTopicInput:
    sequence: int
    title: str
    description: str | None = None
    outcomes: list[BenchmarkOutcomeInput] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkCourseInput:
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    sequence: int
    is_compulsory: bool = True
    course_category: str = "core"
    description: str | None = None
    topics: list[BenchmarkTopicInput] = field(default_factory=list)


@dataclass(slots=True)
class IngestBenchmarkCandidateCommand:
    source_snapshot_id: str
    extractor_version: str
    discipline_group: str
    programme_name: str
    programme_code: str
    version: str
    degree_level: str = "undergraduate"
    minimum_credit_units: int = 120
    courses: list[BenchmarkCourseInput] = field(default_factory=list)


@dataclass(slots=True)
class GetBenchmarkCurriculumCommand:
    curriculum_id: str


@dataclass(slots=True)
class ListBenchmarkCurriculaCommand:
    programme_code: str | None = None
    status: str | None = None


@dataclass(slots=True)
class GetBenchmarkCourseCommand:
    course_id: str


@dataclass(slots=True)
class ListBenchmarkCoursesCommand:
    curriculum_id: str
    level: int | None = None
    semester: int | None = None
