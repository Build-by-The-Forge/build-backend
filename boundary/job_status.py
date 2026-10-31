"""Waiting for an ingestion job to settle. No test dependencies, so the regression
tests in tests/ can import it without the two-service stack.

A failed job with attempts left isn't finished: the retry pass moves it back to
queued. On the gate's short recovery timers that window is about a second, and a
wait stopping there reports a job as failed when it goes on to succeed.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def retry_pending(job: dict[str, Any]) -> bool:
    return job["status"] == "failed" and bool(job["is_retryable"]) and job["attempt_count"] < job["max_attempts"]


def wait_until_settled(
    fetch: Callable[[], dict[str, Any]],
    statuses: set[str],
    timeout: float,
    *,
    interval: float = 0.5,
) -> dict[str, Any]:
    """The job once it reaches one of statuses and no retry is due. Bounded: at
    the timeout it returns the job as it stands, for the caller's assert to report."""
    deadline = time.monotonic() + timeout
    job = fetch()
    while (job["status"] not in statuses or retry_pending(job)) and time.monotonic() < deadline:
        time.sleep(interval)
        job = fetch()
    return job
