from __future__ import annotations

import os
from datetime import date

from app.domain.tenant.academic_session import AcademicSession
from app.domain.tenant.department import Department
from app.domain.tenant.faculty import Faculty
from app.domain.tenant.level import Level
from app.domain.tenant.programme import Programme
from app.domain.tenant.semester import Semester
from app.domain.tenant.tenant import Tenant
from app.domain.tenant.value_objects import (
    AcademicSessionName,
    AcademicSessionSlug,
    DepartmentCode,
    DepartmentName,
    DepartmentSlug,
    FacultyName,
    FacultySlug,
    LevelCode,
    LevelName,
    ProgrammeCode,
    ProgrammeName,
    ProgrammeSlug,
    SemesterName,
    SemesterNumber,
    TenantName,
    TenantSlug,
)
from app.infrastructure.tenant.unit_of_work import TenantUnitOfWork
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./build.db")

# FUTA 9 Schools
FACULTIES = [
    ("School of Computing", "soc"),
    ("School of Engineering and Engineering Technology", "seet"),
    ("School of Environmental Technology", "set"),
    ("School of Agriculture and Agricultural Technology", "saat"),
    ("School of Earth and Mineral Sciences", "sems"),
    ("School of Management Technology", "smt"),
    ("School of Physical Sciences", "sps"),
    ("School of Life Sciences", "sls"),
    ("School of Infrastructure, Minerals and Manufacturing Engineering", "simme"),
]

# 52 Departments sample - REPLACE with your exact list if different
DEPARTMENTS = [
    # SOC - 5
    ("soc", "Computer Science", "csc"),
    ("soc", "Cybersecurity Science", "cys"),
    ("soc", "Software Engineering", "sen"),
    ("soc", "Information Systems", "ifs"),
    ("soc", "Information Technology", "ift"),
    # SEET - 9
    ("seet", "Civil Engineering", "cve"),
    ("seet", "Mechanical Engineering", "mee"),
    ("seet", "Electrical Electronics Engineering", "eee"),
    ("seet", "Chemical Engineering", "che"),
    ("seet", "Biomedical Engineering", "bme"),
    ("seet", "Materials and Metallurgical Engineering", "mme"),
    ("seet", "Industrial and Production Engineering", "ipe"),
    ("seet", "Agricultural and Environmental Engineering", "age"),
    ("seet", "Petroleum and Gas Engineering", "pge"),
    # SET - 7
    ("set", "Architecture", "arc"),
    ("set", "Building Technology", "bdt"),
    ("set", "Estate Management", "esm"),
    ("set", "Quantity Surveying", "qsv"),
    ("set", "Surveying and Geoinformatics", "svg"),
    ("set", "Remote Sensing and Geoinformatics", "rsg"),
    ("set", "Urban and Regional Planning", "urp"),
    # SAAT - 8
    ("saat", "Agricultural Economics and Extension", "aee"),
    ("saat", "Agricultural Production and Management", "apm"),
    ("saat", "Animal Production and Health", "aph"),
    ("saat", "Crop Soil and Pest Management", "csp"),
    ("saat", "Food Science and Technology", "fst"),
    ("saat", "Forestry and Wood Technology", "fwt"),
    ("saat", "Agricultural Extension and Communication", "aec"),
    ("saat", "Aquaculture and Fisheries Management", "afm"),
    # SEMS - 5
    ("sems", "Applied Geology", "agy"),
    ("sems", "Applied Geophysics", "agp"),
    ("sems", "Mining Engineering", "mne"),
    ("sems", "Meteorology and Climate Science", "mcs"),
    ("sems", "Petroleum Chemistry", "ptc"),
    # SMT - 5
    ("smt", "Business Administration", "bam"),
    ("smt", "Entrepreneurship", "ent"),
    ("smt", "Maritime Management", "mmt"),
    ("smt", "Project Management Technology", "pmt"),
    ("smt", "Transport Management Technology", "tmt"),
    # SPS - 4
    ("sps", "Mathematics", "mat"),
    ("sps", "Physics", "phy"),
    ("sps", "Chemistry", "chm"),
    ("sps", "Statistics", "sta"),
    # SLS - 5
    ("sls", "Biochemistry", "bch"),
    ("sls", "Microbiology", "mcb"),
    ("sls", "Biology", "bio"),
    ("sls", "Biotechnology", "btc"),
    ("sls", "Forensic Science", "fsc"),
    # SIMME - 4
    ("simme", "Industrial Design", "ind"),
    ("simme", "Mechanical Engineering Technology", "met"),
    ("simme", "Welding and Fabrication Engineering", "wfe"),
    ("simme", "Chemical Engineering Technology", "cet"),
]


def seed():
    engine = create_engine(DATABASE_URL)
    SessionFactory = sessionmaker(bind=engine)

    with TenantUnitOfWork(SessionFactory) as uow:
        # Check if FUTA exists
        existing = uow.tenants.get_by_slug("futa")
        if existing:
            print(f"FUTA already exists: {existing.id.value}")
            return

        tenant = Tenant.create(name=TenantName("Federal University of Technology Akure"), slug=TenantSlug("futa"))
        uow.tenants.add(tenant)
        print(f"Created tenant FUTA: {tenant.id.value}")

        faculty_map = {}
        for name, slug in FACULTIES:
            f = Faculty.create(tenant_id=tenant.id, name=FacultyName(name), slug=FacultySlug(slug))
            uow.faculties.add(f)
            faculty_map[slug] = f
            print(f" Faculty {slug}")

        dept_map = {}
        for fac_slug, dept_name, dept_code in DEPARTMENTS:
            fac = faculty_map.get(fac_slug)
            if not fac:
                continue
            d = Department.create(
                tenant_id=tenant.id,
                faculty_id=fac.id,
                name=DepartmentName(dept_name),
                code=DepartmentCode(dept_code),
                slug=DepartmentSlug(dept_code),
            )
            uow.departments.add(d)
            dept_map[dept_code] = d
            # Programme per dept
            duration = 6 if dept_code == "arc" else 5
            prog = Programme.create(
                faculty_id=f.id,
                tenant_id=tenant.id,
                department_id=d.id,
                name=ProgrammeName(f"BTech {dept_name}"),
                code=ProgrammeCode(f"btech-{dept_code}"),
                slug=ProgrammeSlug(f"btech-{dept_code}"),
                duration_years=duration,
            )
            uow.programmes.add(prog)

        # Levels 100-500 + 600 for ARC
        for code in [100, 200, 300, 400, 500, 600]:
            level = Level.create(tenant_id=tenant.id, code=LevelCode(code), name=LevelName(f"{code} Level"))
            uow.levels.add(level)
        print(" Levels 100-600")

        # Academic Session 2025/2026
        session = AcademicSession.create(
            tenant_id=tenant.id,
            name=AcademicSessionName("2025/2026"),
            slug=AcademicSessionSlug("2025-2026"),
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_current=True,
        )
        uow.sessions.add(session)
        print(f" Session {session.name.value}")

        # Semesters
        first = Semester.create(
            tenant_id=tenant.id,
            academic_session_id=session.id,
            number=SemesterNumber.FIRST,
            name=SemesterName("First Semester"),
            start_date=date(2025, 9, 1),
            end_date=date(2026, 1, 15),
            is_current=True,
        )
        second = Semester.create(
            tenant_id=tenant.id,
            academic_session_id=session.id,
            number=SemesterNumber.SECOND,
            name=SemesterName("Second Semester"),
            start_date=date(2026, 1, 20),
            end_date=date(2026, 7, 31),
        )
        uow.semesters.add(first)
        uow.semesters.add(second)
        print(" Semesters First/Second")

        uow.commit()
        print("FUTA SEED DONE: tenant futa with 9 faculties, 52 depts, programmes, levels, session, semesters")


if __name__ == "__main__":
    seed()
