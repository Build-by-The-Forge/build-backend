"""An institution's academic structure as a reader sees it. Names are the institution's own,
returned as stored: a School of Computing stays a school, not a generic faculty label."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FacultyEntry:
    id: str
    name: str
    slug: str


@dataclass(frozen=True, slots=True)
class DepartmentEntry:
    id: str
    faculty_id: str
    name: str
    slug: str


@dataclass(frozen=True, slots=True)
class ProgrammeEntry:
    id: str
    faculty_id: str
    department_id: str
    name: str
    slug: str
    code: str
    duration_years: int
