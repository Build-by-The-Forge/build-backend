from uuid import uuid4

import pytest
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
async def test_benchmark_governance_api_flow(client) -> None:
    # 1. Auth setup
    admin_id, admin_token = await register_and_authenticate(client, f"bm-gov-admin-{uuid4()}@example.com")
    _, admin_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, admin_slug)

    student_id, student_token = await register_and_authenticate(client, f"bm-gov-student-{uuid4()}@example.com")
    _, student_slug, _, _ = await seed_tenant_context(student_id, "student")
    student_headers = headers(student_token, student_slug)

    # 2. Source setup
    source_service = build_container().get(CurriculumSourceService)
    source_code = f"NUC_GOV_API_{uuid4().hex[:6].upper()}"
    source = await source_service.register_source(
        code=source_code,
        name="CCMAS Source for Governance API Test",
        base_url="https://ccmas.nuc.edu.ng",
    )
    snap, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/gov_spec.pdf",
        content_sha256="9" * 64,
        raw_artifact_uri="s3://build/gov_spec.pdf",
    )

    prog_code = f"CSC_GOV_{uuid4().hex[:4].upper()}"
    payload = {
        "source_snapshot_id": snap.id,
        "extractor_version": "v1.0",
        "discipline_group": "Computing",
        "programme_name": "Computer Science",
        "programme_code": prog_code,
        "version": "2026.01",
        "degree_level": "undergraduate",
        "minimum_credit_units": 3,
        "courses": [
            {
                "code": "CSC101",
                "title": "Intro to Computer Science",
                "credit_units": 3,
                "level": 100,
                "semester": 1,
                "sequence": 1,
                "is_compulsory": True,
                "course_category": "core",
                "topics": [
                    {
                        "sequence": 1,
                        "title": "Hardware Overview",
                        "description": "CPU and Memory",
                        "outcomes": [
                            {
                                "sequence": 1,
                                "description": "Describe von Neumann architecture.",
                                "bloom_level": "understand",
                            }
                        ],
                    }
                ],
            }
        ],
    }

    # 3. Ingest candidate & validate
    ingest_res = client.post(
        "/curriculum/benchmarks/candidate",
        headers=admin_headers,
        json=payload,
    )
    assert ingest_res.status_code == 201
    curriculum_id = ingest_res.json()["data"]["id"]

    val_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/validate",
        headers=admin_headers,
    )
    assert val_res.status_code == 200

    # 4. Attempt activation without review/approval -> 400 Bad Request
    direct_act = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/activate",
        headers=admin_headers,
    )
    assert direct_act.status_code == 400

    # 5. Student attempt to submit for review -> 403 Forbidden
    student_submit = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/submit-review",
        headers=student_headers,
        json={"notes": "Student trying to submit review"},
    )
    assert student_submit.status_code == 403

    # 6. Admin submits for review -> 200 OK
    submit_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/submit-review",
        headers=admin_headers,
        json={"notes": "Submitted for accreditation review."},
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["data"]["curriculum"]["status"] == "under_review"

    # 7. Admin approves benchmark -> 200 OK
    appr_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/approve",
        headers=admin_headers,
        json={"reason": "Approved by National Curriculum Board."},
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["data"]["curriculum"]["status"] == "approved"

    # 8. Admin activates approved benchmark -> 200 OK
    act_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/activate",
        headers=admin_headers,
    )
    assert act_res.status_code == 200
    assert act_res.json()["data"]["activated"]["status"] == "active"

    # 9. Query audit trail endpoint
    trail_res = client.get(
        f"/curriculum/benchmarks/{curriculum_id}/audit-trail",
        headers=admin_headers,
    )
    assert trail_res.status_code == 200
    logs = trail_res.json()["data"]
    assert len(logs) == 3
    assert [item["action"] for item in logs] == [
        "submit_review",
        "approve",
        "activate",
    ]
