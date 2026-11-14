"""The two-worker dispatch test's failure evidence: enough to tell a retry from a
duplicate claim, and nothing from a task's payload or a tenant."""

import json

from boundary.dispatch_evidence import dispatch_evidence, stream_entries

SENTINEL = "s3://tenant-bucket/secret-object-key-41c9"
TENANT = "00d9d6ad-7280-4de4-bd8e-09a952f12c1a"


def job(job_id, task_id, *, attempt=1, history=()):
    return {
        "id": job_id,
        "tenant_id": TENANT,
        "status": "processing",
        "run_number": 1,
        "attempt_count": attempt,
        "max_attempts": 3,
        "error_code": "AI_DISPATCH_UNCERTAIN" if attempt > 1 else None,
        "is_retryable": attempt > 1,
        "external_task_id": task_id,
        "last_dispatched_at": "2026-11-14T21:33:40Z",
        "attempt_history": list(history),
        "metrics": {"note": SENTINEL},
    }


def entry(entry_id, task_id, job_id, attempt=1):
    task = {
        "task_id": task_id,
        "job_id": job_id,
        "run_number": 1,
        "attempt_count": attempt,
        "tenant_id": TENANT,
        "payload": {"object_key": SENTINEL, "callback_url": "http://backend/cb"},
    }
    return entry_id, {"data": json.dumps(task)}


def report(text):
    assert text.startswith("dispatch evidence:\n")
    return json.loads(text.split("\n", 1)[1])


def test_a_redispatched_job_is_named_with_its_attempts_and_stream_entries():
    jobs = [
        job("job_ok", "task_ok"),
        job("job_twice", "task_2", attempt=2, history=[{"attempt": 1, "error_code": "AI_DISPATCH_UNCERTAIN"}]),
    ]
    entries = [
        entry("1-0", "task_ok", "job_ok"),
        entry("2-0", "task_1", "job_twice"),
        entry("3-0", "task_2", "job_twice", attempt=2),
    ]

    found = report(dispatch_evidence(jobs, entries))

    [affected] = found["affected_jobs"]
    assert affected["id"] == "job_twice" and affected["attempt_count"] == 2
    assert affected["attempt_history"] == [{"attempt": 1, "error_code": "AI_DISPATCH_UNCERTAIN"}]
    # Both of the job's stream entries, so a retry is visible as two tasks.
    assert [(e["entry_id"], e["task_id"]) for e in found["stream_entries_for_affected"]] == [
        ("2-0", "task_1"),
        ("3-0", "task_2"),
    ]


def test_a_task_in_the_stream_twice_marks_its_job_even_on_attempt_one():
    jobs = [job("job_dup", "task_dup")]
    entries = [entry("1-0", "task_dup", "job_dup"), entry("2-0", "task_dup", "job_dup")]

    found = report(dispatch_evidence(jobs, entries))

    assert [j["id"] for j in found["affected_jobs"]] == ["job_dup"]
    assert len(found["stream_entries_for_affected"]) == 2


def test_no_payload_tenant_or_unlisted_field_reaches_the_evidence():
    jobs = [job("job_twice", "task_2", attempt=2)]
    entries = [entry("1-0", "task_1", "job_twice"), entry("2-0", "task_2", "job_twice", attempt=2)]
    groups = [{"name": "workers", "consumers": 2, "pending": 1, "last-delivered-id": "2-0", "lag": 0, "extra": SENTINEL}]

    text = dispatch_evidence(jobs, entries, groups)

    assert SENTINEL not in text and TENANT not in text and "callback_url" not in text
    assert report(text)["consumer_groups"] == [
        {"name": "workers", "consumers": 2, "pending": 1, "last-delivered-id": "2-0", "lag": 0}
    ]


def test_other_tests_entries_are_not_listed():
    """The gate's tests share the stream."""
    jobs = [job("job_twice", "task_2", attempt=2)]
    entries = [
        entry("1-0", "task_other", "job_other"),
        entry("2-0", "task_other", "job_other"),
        entry("3-0", "task_2", "job_twice", attempt=2),
    ]

    found = report(dispatch_evidence(jobs, entries))

    assert [e["entry_id"] for e in found["stream_entries_for_affected"]] == ["3-0"]
    assert found["stream_length_all_tests"] == 3


def test_an_unreadable_entry_is_reported_without_its_content():
    assert stream_entries([("1-0", {"data": "not json " + SENTINEL}), ("2-0", {})]) == [
        {"entry_id": "1-0", "unreadable": True},
        {"entry_id": "2-0", "unreadable": True},
    ]


def test_all_jobs_once_reports_nothing_affected():
    jobs = [job(f"job_{i}", f"task_{i}") for i in range(3)]
    entries = [entry(f"{i}-0", f"task_{i}", f"job_{i}") for i in range(3)]

    found = report(dispatch_evidence(jobs, entries))

    assert found["affected_jobs"] == [] and found["stream_entries_for_affected"] == []
