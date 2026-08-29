import pytest
from app.domain.curriculum.adoption import (
    AdoptionStatus,
    CurriculumOverride,
    InstitutionalAdoption,
    OverrideType,
)


def test_institutional_adoption_lifecycle() -> None:
    adoption = InstitutionalAdoption.create_draft(
        tenant_id="tenant-futa",
        programme_id="prog-csc",
        benchmark_curriculum_id="bmcurr-100",
        benchmark_version="2026.01",
        benchmark_fingerprint="a" * 64,
        academic_session_id="session-2026-2027",
        notes="FUTA adoption for 2026/27 session",
        adopted_by="admin-user-1",
        adopted_by_email="dean@futa.edu.ng",
    )
    assert adoption.status == AdoptionStatus.DRAFT
    assert adoption.is_editable() is True
    assert adoption.benchmark_curriculum_id == "bmcurr-100"
    assert adoption.benchmark_version == "2026.01"
    assert adoption.benchmark_fingerprint == "a" * 64

    # Activate
    adoption.activate(activated_by="admin-user-1")
    assert adoption.status == AdoptionStatus.ACTIVE
    assert adoption.is_editable() is False

    # Activating already active fails
    with pytest.raises(ValueError, match="only draft adoptions can be activated"):
        adoption.activate()

    # Supersede
    adoption.supersede()
    assert adoption.status == AdoptionStatus.SUPERSEDED
    assert adoption.is_editable() is False

    # Superseding non-active fails
    with pytest.raises(ValueError, match="only active adoptions can be superseded"):
        adoption.supersede()


def test_curriculum_override_validation() -> None:
    # 1. Missing mandatory reason raises ValueError
    with pytest.raises(
        ValueError,
        match="academic rationale .* is mandatory for institutional overrides",
    ):
        CurriculumOverride.create(
            adoption_id="adopt-1",
            override_type=OverrideType.MODIFY_COURSE,
            target_course_code="COS102",
            reason="",
            created_by="user-1",
            created_by_email="user@futa.edu.ng",
            field_overrides={"credit_units": 3},
        )

    # 2. Course modification without target_course_code raises ValueError
    with pytest.raises(
        ValueError, match="target_course_code is required for override type"
    ):
        CurriculumOverride.create(
            adoption_id="adopt-1",
            override_type=OverrideType.MODIFY_COURSE,
            target_course_code=None,
            reason="Senate approved 3 units",
            created_by="user-1",
            created_by_email="user@futa.edu.ng",
            field_overrides={"credit_units": 3},
        )

    # 3. Add course without required payload fields raises ValueError
    with pytest.raises(
        ValueError, match="custom_payload for add_course is missing required fields"
    ):
        CurriculumOverride.create(
            adoption_id="adopt-1",
            override_type=OverrideType.ADD_COURSE,
            reason="FUTA general studies requirement",
            created_by="user-1",
            created_by_email="user@futa.edu.ng",
            custom_payload={
                "code": "GNS101"
            },  # missing title, credit_units, level, semester
        )

    # 4. Valid course modification override
    mod_override = CurriculumOverride.create(
        adoption_id="adopt-1",
        override_type=OverrideType.MODIFY_COURSE,
        target_course_code="cos 102",  # normalizes to COS102
        reason="Senate approved 3 units for practical lab component",
        created_by="user-1",
        created_by_email="user@futa.edu.ng",
        field_overrides={"credit_units": 3},
    )
    assert mod_override.target_course_code == "COS102"
    assert mod_override.field_overrides == {"credit_units": 3}
    assert mod_override.id.startswith("ovr-")

    # 5. Valid custom course addition override
    add_override = CurriculumOverride.create(
        adoption_id="adopt-1",
        override_type=OverrideType.ADD_COURSE,
        reason="FUTA mandatory general studies",
        created_by="user-1",
        created_by_email="user@futa.edu.ng",
        custom_payload={
            "code": "GNS101",
            "title": "Use of English & Communication",
            "credit_units": 2,
            "level": 100,
            "semester": 1,
        },
    )
    assert add_override.override_type == OverrideType.ADD_COURSE
    assert add_override.custom_payload["code"] == "GNS101"
