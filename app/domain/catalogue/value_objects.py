from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4


_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CODE_RE = re.compile(r"^[A-Z0-9]{2,20}$")


@dataclass(frozen=True, slots=True)
class CourseId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DepartmentId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProgrammeId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CurriculumVersionId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TopicId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LearningOutcomeId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CoursePrerequisiteId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ReferenceMaterialId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseOfferingId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseCode:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().upper()
        if not _CODE_RE.match(v):
            raise ValueError("course code must be 2-20 uppercase alphanumeric")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseTitle:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 5 or len(v) > 200:
            raise ValueError("course title must be 5-200 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseSlug:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if len(v) < 3 or len(v) > 80:
            raise ValueError("course slug must be 3-80 chars")
        if not _SLUG_RE.match(v):
            raise ValueError("course slug must be lowercase alphanumeric and hyphens only")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseCreditUnits:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0 or self.value > 10:
            raise ValueError("credit units must be between 0 and 10")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseLevel:
    value: int

    def __post_init__(self) -> None:
        if self.value not in (100, 200, 300, 400, 500, 600):
            raise ValueError("course level must be one of 100, 200, 300, 400, 500, 600")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseSemester:
    value: int

    def __post_init__(self) -> None:
        if self.value not in (1, 2):
            raise ValueError("course semester must be 1 or 2")

    def __int__(self) -> int:
        return self.value


class CourseStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class CurriculumVersionName:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 3 or len(v) > 100:
            raise ValueError("curriculum version name must be 3-100 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TopicTitle:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 3 or len(v) > 200:
            raise ValueError("topic title must be 3-200 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TopicSlug:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if len(v) < 3 or len(v) > 80:
            raise ValueError("topic slug must be 3-80 chars")
        if not _SLUG_RE.match(v):
            raise ValueError("topic slug must be lowercase alphanumeric and hyphens only")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TopicDescription:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", self.value.strip())

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LearningOutcomeDescription:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 10 or len(v) > 1000:
            raise ValueError("learning outcome description must be 10-1000 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LearningOutcomeSequence:
    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValueError("learning outcome sequence must be >= 1")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class ReferenceMaterialTitle:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 3 or len(v) > 200:
            raise ValueError("reference material title must be 3-200 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ReferenceMaterialUrl:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) > 0 and not v.startswith("http"):
            raise ValueError("reference material URL must be a valid HTTP/HTTPS URL")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


class CurriculumVersionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TopicLevel(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DETAIL = "detail"


class TopicStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class LearningOutcomeStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PrerequisiteType(str, Enum):
    PRE_REQUISITE = "pre_requisite"
    CO_REQUISITE = "co_requisite"


class PrerequisiteStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReferenceMaterialType(str, Enum):
    PDF = "pdf"
    VIDEO = "video"
    SLIDES = "slides"
    BOOK = "book"
    LINK = "link"


class ReferenceMaterialStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CourseOfferingType(str, Enum):
    REGULAR = "regular"
    SUMMER = "summer"
    LAB = "lab"


class CourseOfferingStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class YearLevel:
    value: int

    def __post_init__(self) -> None:
        if self.value < 100 or self.value > 600:
            raise ValueError("year level must be between 100 and 600")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class SemesterNumber:
    value: int

    def __post_init__(self) -> None:
        if self.value not in (1, 2):
            raise ValueError("semester number must be 1 or 2")

    def __int__(self) -> int:
        return self.value


