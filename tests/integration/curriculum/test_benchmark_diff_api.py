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
async def test_benchmark_diff_api_endpoint(client) -> None:
    # 1. Auth setup
    admin_id, admin_token = await register_and_authenticate(
        client, f"bm-diff-admin-{uuid4()}@example.com"
    )
    _, admin_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, admin_slug)

    # 2. Source setup
    source_service = build_container().get(CurriculumSourceService)
    source_code = f"NUC_DIFF_SRC_{uuid4().hex[:6].upper()}"
    source = await source_service.register_source(
        code=source_code,
        name="CCMAS Source for Diff API Test",
        base_url="https://ccmas.nuc.edu.ng",
    )
    snap1, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/v1.pdf",
        content_sha256="1" * 64,
        raw_artifact_uri="s3://build/v1.pdf",
    )
    snap2, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/v2.pdf",
        content_sha256="2" * 64,
        raw_artifact_uri="s3://build/v2.pdf",
    )

    prog_code = f"CSC_DIFF_{uuid4().hex[:4].upper()}"

    # 3. Ingest V1
    v1_payload = {
        "source_snapshot_id": snap1.id,
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
                "topics": [],
            }
        ],
    }
    v1_res = client.post(
        "/curriculum/benchmarks/candidate",
        headers=admin_headers,
        json=v1_payload,
    )
    assert v1_res.status_code == 201
    v1_id = v1_res.json()["data"]["id"]

    # 4. Ingest V2 (CSC101 modified to 4 CU, CSC102 added with 2 CU)
    v2_payload = {
        "source_snapshot_id": snap2.id,
        "extractor_version": "v1.1",
        "discipline_group": "Computing",
        "programme_name": "Computer Science",
        "programme_code": prog_code,
        "version": "2026.02",
        "degree_level": "undergraduate",
        "minimum_credit_units": 6,
        "courses": [
            {
                "code": "CSC101",
                "title": "Intro to Computer Science",
                "credit_units": 4,  # 3 -> 4
                "level": 100,
                "semester": 1,
                "sequence": 1,
                "is_compulsory": True,
                "course_category": "core",
                "topics": [],
            },
            {
                "code": "CSC102",
                "title": "Programming in C",
                "credit_units": 2,  # added
                "level": 100,
                "semester": 2,
                "sequence": 2,
                "is_compulsory": True,
                "course_category": "core",
                "topics": [],
            },
        ],
    }
    v2_res = client.post(
        "/curriculum/benchmarks/candidate",
        headers=admin_headers,
        json=v2_payload,
    )
    assert v2_res.status_code == 201
    v2_id = v2_res.json()["data"]["id"]

    # 5. Query Diff API
    diff_res = client.get(
        f"/curriculum/benchmarks/diff?source_id={v1_id}&target_id={v2_id}",
        headers=admin_headers,
    )
    assert diff_res.status_code == 200
    diff_data = diff_res.json()
    assert diff_data["success"] is True

    stats = diff_data["data"]["statistics"]
    assert stats["courses_modified"] == 1
    assert stats["courses_added"] == 1
    assert stats["courses_removed"] == 0
    assert stats["credit_units_before"] == 3
    assert stats["credit_units_after"] == 6
    assert stats["credit_units_delta"] == 3
    assert len(diff_data["data"]["diff_fingerprint"]) == 64
