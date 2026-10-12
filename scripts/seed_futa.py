from __future__ import annotations

import logging
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

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./build.db")

# 9 Schools - Canonical FUTA 2025/2026
FACULTIES = [
    ("School of Computing", "soc"),
    ("School of Agriculture and Agricultural Technology", "saat"),
    ("School of Infrastructural, Minerals and Manufacturing Engineering", "simme"),
    ("School of Environmental Technology", "set"),
    ("School of Earth and Mineral Sciences", "sems"),
    ("School of Logistics and Innovation Technology", "slit"),
    ("School of Physical Sciences", "sps"),
    ("School of Life Sciences", "sls"),
    ("School of Electrical and Systems Engineering", "sese"),
]

# 52 Departments - Exact 2025/2026 list
DEPARTMENTS = [
    # SOC - 6
    ("soc", "Computer Science", "csc"),
    ("soc", "Cyber Security", "cys"),
    ("soc", "Information Systems", "ifs"),
    ("soc", "Information Technology", "ift"),
    ("soc", "Software Engineering", "sen"),
    ("soc", "Data Science", "dsc"),
    # SAAT - 9
    ("saat", "Agricultural Extension and Communication Technology", "aec"),
    ("saat", "Agricultural Resources Economics", "are"),
    ("saat", "Animal Production and Health", "aph"),
    ("saat", "Crop, Soil and Pest Management", "csp"),
    ("saat", "Ecotourism and Wildlife Management", "ewm"),
    ("saat", "Fisheries and Aquaculture Technology", "fat"),
    ("saat", "Food Science and Technology", "fst"),
    ("saat", "Forestry and Wood Technology", "fwt"),
    ("saat", "Nutrition and Dietetics", "ntd"),
    # SIMME - 6
    ("simme", "Agricultural Engineering", "age"),
    ("simme", "Civil Engineering", "cve"),
    ("simme", "Industrial and Production Engineering", "ipe"),
    ("simme", "Mechanical Engineering", "mee"),
    ("simme", "Mining Engineering", "mne"),
    ("simme", "Metallurgical and Materials Engineering", "mme"),
    # SET - 7 (ARC is 6yrs, others 5yrs)
    ("set", "Architecture", "arc"),
    ("set", "Building Technology", "bdg"),
    ("set", "Estate Management", "esm"),
    ("set", "Industrial Design", "idd"),
    ("set", "Quantity Surveying", "qsv"),
    ("set", "Urban and Regional Planning", "urp"),
    ("set", "Surveying and Geoinformatics", "svg"),
    # SEMS - 5
    ("sems", "Applied Geology", "agy"),
    ("sems", "Applied Geophysics", "agp"),
    ("sems", "Marine Science and Technology", "mst"),
    ("sems", "Meteorology and Climate Science", "mcs"),
    ("sems", "Remote Sensing and Geoinformatics", "rsg"),
    # SLIT - 5 (PRT & FINTECH new 2025/2026)
    ("slit", "Project Management Technology", "pmt"),
    ("slit", "Logistics and Transport Management Technology", "tmt"),
    ("slit", "Entrepreneurship Management Technology", "ent"),
    ("slit", "Procurement Management Technology", "prt"),
    ("slit", "Financial Technology", "fintech"),
    # SPS - 6
    ("sps", "Chemistry", "chm"),
    ("sps", "Physics", "phy"),
    ("sps", "Mathematical Sciences", "mts"),
    ("sps", "Statistics", "sta"),
    ("sps", "Industrial Mathematics", "imm"),
    ("sps", "Industrial Chemistry", "imc"),
    # SLS - 4
    ("sls", "Biochemistry", "bch"),
    ("sls", "Biology", "bio"),
    ("sls", "Microbiology", "mcb"),
    ("sls", "Biotechnology", "btc"),
    # SESE - 4
    ("sese", "Electrical - Electronics Engineering", "eee"),
    ("sese", "Computer Engineering", "cpe"),
    ("sese", "Information and Communication Engineering", "ice"),
    ("sese", "Biomedical Engineering", "bme"),
]


def seed():
    engine = create_engine(DATABASE_URL)
    SessionFactory = sessionmaker(bind=engine)

    with TenantUnitOfWork(SessionFactory) as uow:
        existing = uow.tenants.get_by_slug("futa")
        if existing:
            log.info(
                "FUTA already exists: %s - deleting and reseeding is recommended for clean state",
                existing.id.value,
            )
            # for clean reseed, uncomment:
            # return

        tenant = Tenant.create(
            name=TenantName("Federal University of Technology Akure"),
            slug=TenantSlug("futa"),
        )
        uow.tenants.add(tenant)
        log.info("Created tenant FUTA: %s", tenant.id.value)

        faculty_map = {}
        for name, slug in FACULTIES:
            f = Faculty.create(tenant_id=tenant.id, name=FacultyName(name), slug=FacultySlug(slug))
            uow.faculties.add(f)
            faculty_map[slug] = f
            log.info(" Faculty %s - %s", slug, name)

        for fac_slug, dept_name, dept_code in DEPARTMENTS:
            fac = faculty_map.get(fac_slug)
            if not fac:
                log.warning(" SKIP %s - faculty %s not found", dept_code, fac_slug)
                continue
            d = Department.create(
                tenant_id=tenant.id,
                faculty_id=fac.id,
                name=DepartmentName(dept_name),
                code=DepartmentCode(dept_code),
                slug=DepartmentSlug(dept_code),
            )
            uow.departments.add(d)
            duration = 6 if dept_code == "arc" else 5
            prog = Programme.create(
                tenant_id=tenant.id,
                faculty_id=fac.id,
                department_id=d.id,
                name=ProgrammeName(f"BTech {dept_name}"),
                code=ProgrammeCode(f"btech-{dept_code}"),
                slug=ProgrammeSlug(f"btech-{dept_code}"),
                duration_years=duration,
            )
            uow.programmes.add(prog)
            log.info(" Dept %s (%sy)", dept_code, duration)

        for code in [100, 200, 300, 400, 500, 600]:
            level = Level.create(
                tenant_id=tenant.id,
                code=LevelCode(code),
                name=LevelName(f"{code} Level"),
            )
            uow.levels.add(level)
        log.info(" Levels 100-600 created")

        acad_session = AcademicSession.create(
            tenant_id=tenant.id,
            name=AcademicSessionName("2025/2026"),
            slug=AcademicSessionSlug("2025-2026"),
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_current=True,
        )
        uow.sessions.add(acad_session)
        log.info(" Session %s", acad_session.name.value)

        first = Semester.create(
            tenant_id=tenant.id,
            academic_session_id=acad_session.id,
            number=SemesterNumber.FIRST,
            name=SemesterName("First Semester"),
            start_date=date(2025, 9, 1),
            end_date=date(2026, 1, 15),
            is_current=True,
        )
        second = Semester.create(
            tenant_id=tenant.id,
            academic_session_id=acad_session.id,
            number=SemesterNumber.SECOND,
            name=SemesterName("Second Semester"),
            start_date=date(2026, 1, 20),
            end_date=date(2026, 7, 31),
        )
        uow.semesters.add(first)
        uow.semesters.add(second)
        log.info(" Semesters First/Second")

        uow.commit()
        log.info(
            "\nFUTA SEED DONE: 9 faculties, %s depts, 52 programmes (ARC=6yrs, others 5yrs), levels, 2025/2026",
            len(DEPARTMENTS),
        )


if __name__ == "__main__":
    seed()
