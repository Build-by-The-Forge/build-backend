"""What the two-worker dispatch test reports when its once-only check fails.

No test dependencies, so the regression tests in tests/ can import it without
the two-service stack.

The check stays strict: every job dispatched once, every task in the AI
service's stream once. This module only makes a failure say why. It names
the affected jobs, their attempts (the backend's own sanitized history) and
the stream entries for them, so a retry after a failed enqueue can be told
apart from a duplicate claim. From each stream entry it reads only
identifiers, never the task's payload, and from each job only fields the
public job response already filters. Tenant IDs are left out.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

# Read from a stream entry's task: identifiers only.
TASK_FIELDS = ("task_id", "job_id", "run_number", "attempt_count")
# Read from a job: what explains its dispatches. error_code and attempt_history
# are already sanitized by the job response (safe_error_code, safe_attempt_record).
JOB_FIELDS = (
    "id",
    "status",
    "run_number",
    "attempt_count",
    "max_attempts",
    "error_code",
    "is_retryable",
    "external_task_id",
    "last_dispatched_at",
    "attempt_history",
)
# A consumer group's counters.
GROUP_FIELDS = ("name", "consumers", "pending", "last-delivered-id", "entries-read", "lag")


def stream_entries(entries: Iterable[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Each entry's ID and its task's identifiers. Nothing else is read."""
    found = []
    for entry_id, fields in entries:
        try:
            task = json.loads(fields.get("data") or "")
        except (TypeError, ValueError):
            task = None
        identifiers = {key: task[key] for key in TASK_FIELDS if key in task} if isinstance(task, dict) else {}
        found.append({"entry_id": entry_id, **identifiers} if identifiers else {"entry_id": entry_id, "unreadable": True})
    return found


def dispatch_evidence(
    jobs: Iterable[Mapping[str, Any]],
    entries: Iterable[tuple[str, Mapping[str, Any]]],
    groups: Iterable[Mapping[str, Any]] = (),
) -> str:
    """The failure message: every job dispatched other than once, and why it might be."""
    jobs = list(jobs)
    stream = stream_entries(entries)
    per_task = Counter(entry.get("task_id") for entry in stream)
    per_job = Counter(entry.get("job_id") for entry in stream)

    affected = [
        job
        for job in jobs
        if job.get("attempt_count") != 1
        or not job.get("external_task_id")
        or per_task[job.get("external_task_id")] != 1
        or per_job[job.get("id")] > 1
    ]
    # The gate's tests share the stream: only entries tied to these affected jobs
    # by their own job or task ID are listed. An entry without either, such as
    # an unreadable one, is never listed: it is counted.
    affected_ids = {job.get("id") for job in affected} - {None}
    affected_tasks = {job.get("external_task_id") for job in affected} - {None}

    report = {
        "jobs": len(jobs),
        "affected_jobs": [{key: job.get(key) for key in JOB_FIELDS} for job in affected],
        "stream_length_all_tests": len(stream),
        "stream_entries_for_affected": [
            entry for entry in stream if entry.get("job_id") in affected_ids or entry.get("task_id") in affected_tasks
        ],
        "unreadable_entries_all_tests": sum(1 for entry in stream if entry.get("unreadable")),
        "consumer_groups": [{key: group[key] for key in GROUP_FIELDS if key in group} for group in groups],
    }
    return "dispatch evidence:\n" + json.dumps(report, indent=1, sort_keys=True, default=str)
