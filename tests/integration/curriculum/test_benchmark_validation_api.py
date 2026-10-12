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
async def test_validate_benchmark_candidate_api(client) -> None:
    # 1. Auth setup
    admin_id, admin_token = await register_and_authenticate(client, f"bm-val-admin-{uuid4()}@example.com")
    _, admin_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, admin_slug)

    student_id, student_token = await register_and_authenticate(client, f"bm-val-student-{uuid4()}@example.com")
    _, student_slug, _, _ = await seed_tenant_context(student_id, "student")
    student_headers = headers(student_token, student_slug)

    # 2. Seed Source & Snapshot
    source_service = build_container().get(CurriculumSourceService)
    source_code = f"NUC_VAL_SRC_{uuid4().hex[:6].upper()}"
    source = await source_service.register_source(
        code=source_code,
        name="CCMAS Source for Validation API Test",
        base_url="https://ccmas.nuc.edu.ng",
    )
    snap, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/csc_val.pdf",
        content_sha256="5" * 64,
        raw_artifact_uri="s3://build/csc_val.pdf",
    )

    prog_code = f"CSC_VAL_{uuid4().hex[:4].upper()}"
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
    assert ingest_res.json()["data"]["status"] == "candidate"

    # 4. Student validate attempt -> 403 Forbidden
    student_val_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/validate",
        headers=student_headers,
    )
    assert student_val_res.status_code == 403

    # 5. Admin validate candidate -> 200 OK
    admin_val_res = client.post(
        f"/curriculum/benchmarks/{curriculum_id}/validate",
        headers=admin_headers,
    )
    assert admin_val_res.status_code == 200
    val_data = admin_val_res.json()
    assert val_data["success"] is True
    assert val_data["data"]["curriculum"]["status"] == "validated"
    assert val_data["data"]["validation"]["is_valid"] is True
    assert val_data["meta"]["error_count"] == 0
