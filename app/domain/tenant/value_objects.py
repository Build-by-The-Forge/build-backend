from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CODE_RE = re.compile(r"^[A-Z0-9]{2,20}$")
_PROG_CODE_RE = re.compile(r"^[A-Z0-9-]{2,30}$")


@dataclass(frozen=True, slots=True)
class TenantId:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip() if self.value else ""
        if not v:
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TenantName:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 2 or len(v) > 100:
            raise ValueError("tenant name must be 2-100 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TenantSlug:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if len(v) < 3 or len(v) > 50:
            raise ValueError("tenant slug must be 3-50 chars")
        if not _SLUG_RE.match(v):
            raise ValueError("tenant slug must be lowercase alphanumeric and hyphens only")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


class TenantStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class FacultyId:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip() if self.value else ""
        if not v:
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FacultyName:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 2 or len(v) > 100:
            raise ValueError("faculty name must be 2-100 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FacultySlug:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if len(v) < 3 or len(v) > 50:
            raise ValueError("faculty slug must be 3-50 chars")
        if not _SLUG_RE.match(v):
            raise ValueError("faculty slug must be lowercase alphanumeric and hyphens only")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


class FacultyStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class DepartmentId:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip() if self.value else ""
        if not v:
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DepartmentName:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 2 or len(v) > 100:
            raise ValueError("department name must be 2-100 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DepartmentSlug:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if len(v) < 3 or len(v) > 50:
            raise ValueError("department slug must be 3-50 chars")
        if not _SLUG_RE.match(v):
            raise ValueError("department slug must be lowercase alphanumeric and hyphens only")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DepartmentCode:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().upper()
        if not _CODE_RE.match(v):
            raise ValueError("department code must be 2-20 uppercase alphanumeric")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


class DepartmentStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ProgrammeId:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip() if self.value else ""
        if not v:
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProgrammeName:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 2 or len(v) > 150:
            raise ValueError("programme name must be 2-150 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProgrammeSlug:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if len(v) < 3 or len(v) > 80:
            raise ValueError("programme slug must be 3-80 chars")
        if not _SLUG_RE.match(v):
            raise ValueError("programme slug must be lowercase alphanumeric and hyphens only")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProgrammeCode:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().upper()
        if not _PROG_CODE_RE.match(v):
            raise ValueError("programme code must be 2-30 uppercase alphanumeric and hyphens")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


class ProgrammeStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class LevelId:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip() if self.value else ""
        if not v:
            object.__setattr__(self, "value", str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LevelCode:
    value: int

    def __post_init__(self) -> None:
        v = self.value
        if v not in (100, 200, 300, 400, 500, 600, 700):
            raise ValueError("level code must be one of 100, 200, 300, 400, 500, 600, 700")

    def __str__(self) -> str:
        return str(self.value)

    @property
    def is_final_for_futa(self) -> bool:
        return self.value == 500

    @property
    def is_final_for_architecture(self) -> bool:
        return self.value == 600


@dataclass(frozen=True, slots=True)
class LevelName:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip()
        if len(v) < 2 or len(v) > 50:
            raise ValueError("level name must be 2-50 chars")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


class LevelStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
