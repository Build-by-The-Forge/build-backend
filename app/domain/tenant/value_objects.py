from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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


# ---- Faculty ----


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
