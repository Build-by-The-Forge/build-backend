from uuid import uuid4

import pytest

from app.application.curriculum.benchmark_commands import (
    BenchmarkCourseInput,
    BenchmarkOutcomeInput,
    BenchmarkTopicInput,
)
from app.application.curriculum.benchmark_service import (
    BenchmarkCurriculumService,
)
from app.application.curriculum.curriculum_source_service import (
    CurriculumSourceService,
)
from app.bootstrap.container import build_container
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


@pytest.mark.asyncio
async def test_effective_curriculum_api_endpoints(client) -> None:
    # 1. Tenant A (FUTA) Setup
    admin_a_id, admin_a_token = await register_and_authenticate(client, f"futa-eff-admin-{uuid4()}@example.com")
    tenant_a_id, tenant_a_slug, _, _ = await seed_tenant_context(admin_a_id, "admin")
    admin_a_headers = headers(admin_a_token, tenant_a_slug)

    student_a_id, student_a_token = await register_and_authenticate(client, f"futa-eff-student-{uuid4()}@example.com")
    from tests.integration.assessment.test_attempt_api import add_membership

    await add_membership(student_a_id, tenant_a_id, "student")
    student_a_headers = headers(student_a_token, tenant_a_slug)

    # Tenant B (UNILAG) Setup
    admin_b_id, admin_b_token = await register_and_authenticate(client, f"unilag-eff-admin-{uuid4()}@example.com")
    _, tenant_b_slug, _, _ = await seed_tenant_context(admin_b_id, "admin")
    admin_b_headers = headers(admin_b_token, tenant_b_slug)

    # 2. Benchmark Setup
    source_service = build_container().get(CurriculumSourceService)
    benchmark_service = build_container().get(BenchmarkCurriculumService)

    source = await source_service.register_source(
        code=f"NUC_EFF_API_{uuid4().hex[:6].upper()}",
        name="CCMAS for Effective API",
        base_url="https://ccmas.nuc.edu.ng",
    )
    snap, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/spec.pdf",
        content_sha256="4" * 64,
        raw_artifact_uri="s3://build/spec.pdf",
    )

    prog_code = f"CSC_EFF_{uuid4().hex[:4].upper()}"
    bm, _ = await benchmark_service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code=prog_code,
        version="2026.01",
        minimum_credit_units=3,
        courses=[
            BenchmarkCourseInput(
                code="CSC101",
                title="Intro to Computing",
                credit_units=3,
                level=100,
                semester=1,
                sequence=1,
                topics=[
                    BenchmarkTopicInput(
                        sequence=1,
                        title="Basics",
                        outcomes=[
                            BenchmarkOutcomeInput(
                                sequence=1,
                                description="Understand basics.",
                                bloom_level="understand",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    await benchmark_service.validate_candidate(bm.id)
    await benchmark_service.submit_for_review(bm.id, actor_id="nuc-admin", actor_email="admin@nuc.edu.ng")
    await benchmark_service.approve_curriculum(
        bm.id,
        reviewer_id="nuc-lead",
        reviewer_email="lead@nuc.edu.ng",
        reason="Approved",
    )
    await benchmark_service.activate_curriculum(bm.id, activated_by="nuc-admin")

    # 3. Tenant A Adopts Benchmark
    prog_id = "prog-futa-csc"
    adopt_res = client.post(
        "/curriculum/adoptions",
        headers=admin_a_headers,
        json={
            "programme_id": prog_id,
            "benchmark_curriculum_id": bm.id,
            "academic_session_id": "2026-2027",
            "notes": "FUTA 2026/27 adoption",
        },
    )
    assert adopt_res.status_code == 201
    adoption_id = adopt_res.json()["data"]["id"]

    # 4. Add Course Modification (CSC101 -> 4 units)
    override_res = client.post(
        f"/curriculum/adoptions/{adoption_id}/overrides",
        headers=admin_a_headers,
        json={
            "override_type": "modify_course",
            "target_course_code": "CSC101",
            "field_overrides": {"credit_units": 4},
            "reason": "Senate practical laboratory requirement.",
        },
    )
    assert override_res.status_code == 201

    # 5. Activate Adoption
    act_res = client.post(
        f"/curriculum/adoptions/{adoption_id}/activate",
        headers=admin_a_headers,
    )
    assert act_res.status_code == 200

    # 6. Admin queries Full Effective Curriculum by Adoption ID -> 200 OK
    admin_eff_res = client.get(
        f"/curriculum/adoptions/{adoption_id}/effective",
        headers=admin_a_headers,
    )
    assert admin_eff_res.status_code == 200
    admin_data = admin_eff_res.json()["data"]
    assert admin_data["statistics"]["total_credit_units"] == 4
    assert admin_data["courses"][0]["origin"] == "institutional_modified"
    assert len(admin_data["courses"][0]["applied_overrides"]) == 1
    assert admin_data["courses"][0]["applied_overrides"][0]["reason"] == "Senate practical laboratory requirement."

    # 7. Student queries Student Read Mode Active Curriculum -> 200 OK
    student_eff_res = client.get(
        f"/curriculum/adoptions/effective/active/{prog_id}",
        headers=student_a_headers,
    )
    assert student_eff_res.status_code == 200
    student_data = student_eff_res.json()["data"]
    assert student_data["total_credit_units"] == 4
    assert student_data["courses"][0]["code"] == "CSC101"
    assert student_data["courses"][0]["credit_units"] == 4
    # Student view does not expose applied_overrides
    assert "applied_overrides" not in student_data["courses"][0]

    # 8. Tenant B (UNILAG) attempts to access Tenant A's adoption effective resolution -> 404 Not Found
    tenant_b_res = client.get(
        f"/curriculum/adoptions/{adoption_id}/effective",
        headers=admin_b_headers,
    )
    assert tenant_b_res.status_code == 404
