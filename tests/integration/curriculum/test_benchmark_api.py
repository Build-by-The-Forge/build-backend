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
async def test_benchmark_curriculum_api_endpoints(client) -> None:
    # 1. Admin setup
    admin_id, admin_token = await register_and_authenticate(
        client, f"bm-admin-{uuid4()}@example.com"
    )
    _, admin_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, admin_slug)

    # 2. Lecturer setup
    lecturer_id, lecturer_token = await register_and_authenticate(
        client, f"bm-lecturer-{uuid4()}@example.com"
    )
    _, lecturer_slug, _, _ = await seed_tenant_context(lecturer_id, "lecturer")
    lecturer_headers = headers(lecturer_token, lecturer_slug)

    # 3. Student setup
    student_id, student_token = await register_and_authenticate(
        client, f"bm-student-{uuid4()}@example.com"
    )
    _, student_slug, _, _ = await seed_tenant_context(student_id, "student")
    student_headers = headers(student_token, student_slug)

    # 4. Seed Source & Snapshot
    source_service = build_container().get(CurriculumSourceService)
    source_code = f"NUC_SRC_{uuid4().hex[:6].upper()}"
    source = await source_service.register_source(
        code=source_code,
        name="CCMAS Source for Benchmark API Test",
        base_url="https://ccmas.nuc.edu.ng",
    )
    snap, _ = await source_service.record_snapshot(
        source_id=source.id,
        source_url="https://ccmas.nuc.edu.ng/csc.pdf",
        content_sha256="7" * 64,
        raw_artifact_uri="s3://build/csc.pdf",
    )

    prog_code = f"CSC_{uuid4().hex[:4].upper()}"
    payload = {
        "source_snapshot_id": snap.id,
        "extractor_version": "v1.0-gemini",
        "discipline_group": "Computing",
        "programme_name": "Computer Science",
        "programme_code": prog_code,
        "version": "2026.01",
        "degree_level": "undergraduate",
        "minimum_credit_units": 120,
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
                "description": "Overview of computing systems.",
                "topics": [
                    {
                        "sequence": 1,
                        "title": "Computer Hardware & Software",
                        "description": "Hardware architecture overview",
                        "outcomes": [
                            {
                                "sequence": 1,
                                "description": "Distinguish between systems and applications.",
                                "bloom_level": "understand",
                            }
                        ],
                    }
                ],
            }
        ],
    }

    # 5. Student attempt to ingest -> 403 Forbidden
    student_ingest = client.post(
        "/curriculum/benchmarks/candidate",
        headers=student_headers,
        json=payload,
    )
    assert student_ingest.status_code == 403

    # 6. Admin ingests candidate -> 201 Created
    admin_ingest = client.post(
        "/curriculum/benchmarks/candidate",
        headers=admin_headers,
        json=payload,
    )
    assert admin_ingest.status_code == 201, admin_ingest.text
    ingest_data = admin_ingest.json()
    curriculum_id = ingest_data["data"]["id"]
    assert ingest_data["data"]["programme_code"] == prog_code
    assert ingest_data["meta"]["created"] is True

    # 7. Re-ingestion of same snapshot + programme -> 200 OK (created=False)
    re_ingest = client.post(
        "/curriculum/benchmarks/candidate",
        headers=admin_headers,
        json=payload,
    )
    assert re_ingest.status_code == 200
    assert re_ingest.json()["meta"]["created"] is False

    # 8. Lecturer lists benchmarks -> 200 OK
    list_res = client.get(
        f"/curriculum/benchmarks?programme_code={prog_code}",
        headers=lecturer_headers,
    )
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) == 1

    # 9. Lecturer gets benchmark header -> 200 OK
    get_res = client.get(
        f"/curriculum/benchmarks/{curriculum_id}",
        headers=lecturer_headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["data"]["programme_code"] == prog_code

    # 10. Lecturer lists courses -> 200 OK
    courses_res = client.get(
        f"/curriculum/benchmarks/{curriculum_id}/courses?level=100",
        headers=lecturer_headers,
    )
    assert courses_res.status_code == 200
    courses = courses_res.json()["data"]
    assert len(courses) == 1
    course_id = courses[0]["id"]
    assert courses[0]["code"] == "COS101"

    # 11. Lecturer gets full course detail -> 200 OK
    course_detail_res = client.get(
        f"/curriculum/benchmarks/{curriculum_id}/courses/{course_id}",
        headers=lecturer_headers,
    )
    assert course_detail_res.status_code == 200
    course_detail = course_detail_res.json()["data"]
    assert course_detail["code"] == "COS101"
    assert len(course_detail["topics"]) == 1
    assert course_detail["topics"][0]["title"] == "Computer Hardware & Software"
    assert len(course_detail["topics"][0]["outcomes"]) == 1
