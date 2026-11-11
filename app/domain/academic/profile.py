"""The student's academic profile (S-02): programme, level and enrolled courses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Bounds the course rows and the response size; a full semester load is well under it.
MAX_COURSES = 30


@dataclass(frozen=True)
class ProfileProgramme:
    id: str
    name: str
    code: str


@dataclass(frozen=True)
class ProfileUnit:
    id: str
    name: str


@dataclass(frozen=True)
class ProfileCourse:
    id: str
    code: str
    title: str
    level: int
    semester: int
    credit_units: int


@dataclass(frozen=True)
class AcademicProfile:
    """As a student reads it: anything they can no longer read is left out
    (decision 4). Department and faculty are the programme's."""

    programme: ProfileProgramme | None = None
    department: ProfileUnit | None = None
    faculty: ProfileUnit | None = None
    level: int | None = None
    courses: list[ProfileCourse] = field(default_factory=list)
    updated_at: datetime | None = None

    @property
    def complete(self) -> bool:
        return self.programme is not None and self.level is not None


class UnavailableReferences(Exception):
    """A save named something a student of the tenant can't read: it doesn't
    exist, belongs to another tenant, or is archived. One answer for all
    three, naming only the fields."""

    def __init__(self, fields: list[str]) -> None:
        super().__init__("unavailable: " + ", ".join(fields))
        self.fields = fields


class NotAStudentMember(Exception):
    """The caller has no active student membership in the tenant. Checked
    where the profile is read and written, not only by the route: owners and
    admins hold every permission, and a profile is only ever a student's."""
