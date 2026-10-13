from uuid import UUID, uuid4

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
async def test_institutional_adoption_api_and_tenant_isolation(client) -> None:
    # 1. Tenant A (FUTA) admin and student setup
    admin_a_id, admin_a_token = await register_and_authenticate(
        client, f"futa-admin-{uuid4()}@example.com"
    )
    _, tenant_a_slug, _, _ = await seed_tenant_context(admin_a_id, "admin")
    admin_a_headers = headers(admin_a_token, tenant_a_slug)

    student_a_id, student_a_token = await register_and_authenticate(
        client, f"futa-student-{uuid4()}@example.com"
    )
    _, _, _, _ = await seed_tenant_context(student_a_id, "student")
    student_a_headers = headers(student_a_token, tenant_a_slug)

    # Tenant B (UNILAG) admin setup
    admin_b_id, admin_b_token = await register_and_authenticate(
        client, f"unilag-admin-{uuid4()}@example.com"
    )
    _, tenant_b_slug, _, _ = await seed_tenant_context(admin_b_id, "admin")
    admin_b_headers = headers(admin_b_token, tenant_b_slug)

    # 2. Seed active Benchmark Curriculum
    source_service = build_container().get(CurriculumSourceService)
    benchmark_service = build_container().get(BenchmarkCurriculumService)

    source = await source_service.register_source(
        code=f"NUC_ADOPT_API_{uuid4().hex[:6].upper()}",
        name="CCMAS for Adoption API",
        base_url="https://ccmas.nuc.edu.ng",
    )
    snap, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/spec.pdf",
        content_sha256="7" * 64,
        raw_artifact_uri="s3://build/spec.pdf",
    )

    prog_code = f"CSC_AD_{uuid4().hex[:4].upper()}"
    benchmark_candidate, _ = await benchmark_service.ingest_candidate(
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
    await benchmark_service.validate_candidate(benchmark_candidate.id)
    await benchmark_service.submit_for_review(
        benchmark_candidate.id, actor_id="nuc-admin", actor_email="nuc@build.internal"
    )
    await benchmark_service.approve_curriculum(
        benchmark_candidate.id,
        reviewer_id="nuc-lead",
        reviewer_email="lead@build.internal",
        reason="Approved national standard",
    )
    await benchmark_service.activate_curriculum(
        curriculum_id=benchmark_candidate.id,
        activated_by="nuc-admin",
    )

    # 3. Student attempt to adopt -> 403 Forbidden
    student_adopt = client.post(
        "/curriculum/adoptions",
        headers=student_a_headers,
        json={
            "programme_id": "prog-futa-csc",
            "benchmark_curriculum_id": benchmark_candidate.id,
            "academic_session_id": "2026-2027",
            "notes": "Student trying to adopt",
        },
    )
    assert student_adopt.status_code == 403

    # 4. Tenant A Admin adopts benchmark -> 201 Created
    adopt_res = client.post(
        "/curriculum/adoptions",
        headers=admin_a_headers,
        json={
            "programme_id": "prog-futa-csc",
            "benchmark_curriculum_id": benchmark_candidate.id,
            "academic_session_id": "2026-2027",
            "notes": "FUTA 2026/27 adoption",
        },
    )
    assert adopt_res.status_code == 201
    adoption_id = adopt_res.json()["data"]["id"]
    assert adopt_res.json()["data"]["status"] == "draft"
    assert adopt_res.json()["data"]["benchmark_version"] == "2026.01"

    # 5. Tenant A adds a Course Modification override -> 201 Created
    override_res = client.post(
        f"/curriculum/adoptions/{adoption_id}/overrides",
        headers=admin_a_headers,
        json={
            "override_type": "modify_course",
            "target_course_code": "CSC101",
            "field_overrides": {"credit_units": 4},
            "reason": "Senate approved 4 units for practical lab.",
        },
    )
    assert override_res.status_code == 201
    override_id = override_res.json()["data"]["id"]
    assert str(UUID(override_id)) == override_id  # fits VARCHAR(36)
    assert override_res.json()["data"]["field_overrides"]["credit_units"] == 4

    # 6. Tenant B (UNILAG) attempts to view Tenant A's adoption -> 404 Not Found (Tenant Isolation)
    tenant_b_view = client.get(
        f"/curriculum/adoptions/{adoption_id}",
        headers=admin_b_headers,
    )
    assert tenant_b_view.status_code == 404

    # 7. Tenant A gets adoption detail -> 200 OK
    detail_res = client.get(
        f"/curriculum/adoptions/{adoption_id}",
        headers=admin_a_headers,
    )
    assert detail_res.status_code == 200
    assert len(detail_res.json()["data"]["overrides"]) == 1

    # 8. Tenant A activates adoption -> 200 OK
    act_res = client.post(
        f"/curriculum/adoptions/{adoption_id}/activate",
        headers=admin_a_headers,
    )
    assert act_res.status_code == 200
    assert act_res.json()["data"]["activated"]["status"] == "active"

    # 9. List adoptions for Tenant A
    list_res = client.get(
        "/curriculum/adoptions",
        headers=admin_a_headers,
    )
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) >= 1
