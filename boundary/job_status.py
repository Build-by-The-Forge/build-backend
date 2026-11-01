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


class JobNotSettled(AssertionError):
    """The deadline passed first. A job failed with a retry due is not a failed
    job, so it is never handed back for a caller to read as an outcome."""

    def __init__(self, job: dict[str, Any], timeout: float) -> None:
        super().__init__(f"job not settled after {timeout} s: {job}")
        self.job = job


def retry_pending(job: dict[str, Any]) -> bool:
    return job["status"] == "failed" and bool(job["is_retryable"]) and job["attempt_count"] < job["max_attempts"]


def attempt_finished(job: dict[str, Any], attempt: int) -> bool:
    """Takes one read of the job. The retry pass moves failed on attempt N to queued
    on attempt N + 1 at once, so a status from one read and an attempt from the next
    can describe a state the job was never in."""
    return job["attempt_count"] == attempt and job["status"] in ("ready", "failed")


def wait_until_idle(
    fetch_busy: Callable[[], list[Any]],
    timeout: float,
    *,
    interval: float = 0.5,
) -> None:
    """Until no earlier work can reach a fault point. A pause file holds whichever
    job gets there first, and the fault worker runs one task at a time: an earlier
    job taking the hold leaves the test's own job waiting behind it."""
    deadline = time.monotonic() + timeout
    busy = fetch_busy()
    while busy:
        if time.monotonic() >= deadline:
            raise AssertionError(f"still busy after {timeout} s: {busy}")
        time.sleep(interval)
        busy = fetch_busy()


def wait_until_settled(
    fetch: Callable[[], dict[str, Any]],
    statuses: set[str],
    timeout: float,
    *,
    interval: float = 0.5,
) -> dict[str, Any]:
    """The job once it reaches one of statuses and no retry is due. A returned job
    has settled. At the timeout this raises JobNotSettled, and it never returns
    a job still on its way."""
    deadline = time.monotonic() + timeout
    job = fetch()
    while job["status"] not in statuses or retry_pending(job):
        if time.monotonic() >= deadline:
            raise JobNotSettled(job, timeout)
        time.sleep(interval)
        job = fetch()
    return job
