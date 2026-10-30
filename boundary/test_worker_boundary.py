"""Worker concurrency checks against the real backend, AI-service and Redis."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter

from redis import Redis

from boundary.conftest import create_job_for, create_source, pdf_document, upload

JOB_COUNT = 50
TASK_STREAM = "{ai-tasks}:stream:ai_tasks"


def test_two_workers_dispatch_fifty_jobs_once(backend, tenant_a):
    source_id = create_source(backend, tenant_a)
    expected_job_ids: set[str] = set()

    for _ in range(JOB_COUNT):
        response = upload(backend, tenant_a, source_id, pdf_document(uuid.uuid4().hex))
        assert response.status_code == 201, response.text
        job = create_job_for(backend, tenant_a, response.json()["data"])
        expected_job_ids.add(job["id"])

    deadline = time.time() + 180
    jobs = []
    while time.time() < deadline:
        response = backend.get(
            "/content/jobs",
            params={"source_id": source_id, "limit": 100},
            headers=tenant_a.h("lecturer"),
        )
        assert response.status_code == 200, response.text
        jobs = response.json()["data"]
        if len(jobs) == JOB_COUNT and all(job["external_task_id"] for job in jobs):
            break
        time.sleep(0.5)

    assert {job["id"] for job in jobs} == expected_job_ids
    assert all(job["external_task_id"] for job in jobs), jobs
    assert all(job["attempt_count"] == 1 for job in jobs), jobs
    task_ids = [job["external_task_id"] for job in jobs]
    assert len(set(task_ids)) == JOB_COUNT, task_ids

    redis_client = Redis.from_url(os.environ["BOUNDARY_AI_REDIS_URL"], decode_responses=True)
    try:
        entries = redis_client.xrange(TASK_STREAM)
    finally:
        redis_client.close()

    stream_counts = Counter(json.loads(fields["data"])["task_id"] for _, fields in entries)
    assert {task_id: stream_counts[task_id] for task_id in task_ids} == {task_id: 1 for task_id in task_ids}
