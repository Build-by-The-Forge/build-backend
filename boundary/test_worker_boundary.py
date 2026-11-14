"""Worker concurrency checks against the real backend, AI-service and Redis."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter

from redis import Redis
from redis.exceptions import ResponseError

from boundary.conftest import create_job_for, create_source, pdf_document, upload
from boundary.dispatch_evidence import dispatch_evidence

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

    # Read once, before any check, so every failure below carries the same evidence:
    # the affected jobs, their attempts and their stream entries (identifiers only).
    redis_client = Redis.from_url(os.environ["BOUNDARY_AI_REDIS_URL"], decode_responses=True)
    try:
        entries = redis_client.xrange(TASK_STREAM)
        try:
            groups = redis_client.xinfo_groups(TASK_STREAM)
        except ResponseError:  # no group yet: evidence only, never the check
            groups = []
    finally:
        redis_client.close()
    evidence = dispatch_evidence(jobs, entries, groups)

    assert {job["id"] for job in jobs} == expected_job_ids, evidence
    assert all(job["external_task_id"] for job in jobs), evidence
    assert all(job["attempt_count"] == 1 for job in jobs), evidence
    task_ids = [job["external_task_id"] for job in jobs]
    assert len(set(task_ids)) == JOB_COUNT, evidence

    stream_counts = Counter(json.loads(fields["data"])["task_id"] for _, fields in entries)
    assert {task_id: stream_counts[task_id] for task_id in task_ids} == {task_id: 1 for task_id in task_ids}, evidence
