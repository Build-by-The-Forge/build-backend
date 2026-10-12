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
async def test_activate_benchmark_curriculum_api(client) -> None:
    # 1. Auth setup
    admin_id, admin_token = await register_and_authenticate(client, f"bm-act-admin-{uuid4()}@example.com")
    _, admin_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, admin_slug)

    student_id, student_token = await register_and_authenticate(client, f"bm-act-student-{uuid4()}@example.com")
    _, student_slug, _, _ = await seed_tenant_context(student_id, "student")
    student_headers = headers(student_token, student_slug)

    # 2. Seed Source & Snapshot
    source_service = build_container().get(CurriculumSourceService)
    source_code = f"NUC_ACT_SRC_{uuid4().hex[:6].upper()}"
    source = await source_service.register_source(
        code=source_code,
        name="CCMAS Source for Activation API Test",
        base_url="https://ccmas.nuc.edu.ng",
    )
    snap, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/csc_act.pdf",
        content_sha256="4" * 64,
        raw_artifact_uri="s3://build/csc_act.pdf",
    )

    prog_code = f"CSC_ACT_{uuid4().hex[:4].upper()}"
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
                "code": "COS101",
                "title": "Introduction to Computer Science",
                "credit_units": 3,
                "level": 100,
                "semester": 1,
                "sequence": 1,
                "is_compulsory": True,
                "course_category": "core",
                "description": "Hardware architecture overview",
                "topics": [
                    {
                        "sequence": 1,
                        "title": "Von Neumann Architecture",
                        "description": "CPU and Memory",
                        "outcomes": [
                            {
                                "sequence": 1,
                                "description": "Identify CPU components.",
                                "bloom_level": "remember",
                            }
                        ],
                    }
                ],
            }
        ],
    }

    # 3. Ingest candidate as admin
    ingest_res = client.post(
        "/curriculum/benchmarks/candidate",
        headers=admin_headers,
        json=payload,
    )
    assert ingest_res.status_code == 201
    curriculum_id = ingest_res.json()["data"]["id"]

    # 4. Activate without validation -> 400 Bad Request
    unvalidated_act = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/activate",
        headers=admin_headers,
    )
    assert unvalidated_act.status_code == 400

    # 5. Validate candidate
    val_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/validate",
        headers=admin_headers,
    )
    assert val_res.status_code == 200

    # 6. Attempt activation directly from VALIDATED -> 400 Bad Request
    unapproved_act = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/activate",
        headers=admin_headers,
    )
    assert unapproved_act.status_code == 400

    # 7. Submit for review & Approve
    submit_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/submit-review",
        headers=admin_headers,
        json={"notes": "Ready for approval"},
    )
    assert submit_res.status_code == 200

    appr_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/approve",
        headers=admin_headers,
        json={"reason": "Approved standard"},
    )
    assert appr_res.status_code == 200

    # 8. Student attempt to activate -> 403 Forbidden
    student_act = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/activate",
        headers=student_headers,
    )
    assert student_act.status_code == 403

    # 9. Admin activates approved curriculum -> 200 OK
    admin_act = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/activate",
        headers=admin_headers,
    )
    assert admin_act.status_code == 200
    act_data = admin_act.json()
    assert act_data["success"] is True
    assert act_data["data"]["activated"]["status"] == "active"
    assert act_data["data"]["superseded"] is None

    # 10. Query active benchmark endpoint
    get_active = client.get(
        f"/curriculum/benchmarks/active/Computing/{prog_code}",
        headers=admin_headers,
    )
    assert get_active.status_code == 200
    assert get_active.json()["data"]["id"] == curriculum_id
    assert get_active.json()["data"]["status"] == "active"
