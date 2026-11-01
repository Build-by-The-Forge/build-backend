"""The boundary suite's wait: a failure with a retry due isn't the job's outcome."""

import re
from pathlib import Path

import pytest

from boundary.job_status import (
    JobNotSettled,
    attempt_finished,
    retry_pending,
    wait_until_idle,
    wait_until_settled,
)

SETTLED = {"ready", "failed"}


def job(status, *, retryable=False, attempt=1, maximum=3):
    return {"status": status, "is_retryable": retryable, "attempt_count": attempt, "max_attempts": maximum}


def sequence(*jobs):
    """Each fetch moves on one step; the last repeats."""
    remaining = list(jobs)

    def fetch():
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return fetch


def wait(fetch, timeout=5.0):
    return wait_until_settled(fetch, SETTLED, timeout, interval=0)


def test_a_transient_failure_followed_by_a_retry_ends_ready():
    # The gate failure this fixes: failed for a moment, then queued, then ready.
    final = wait(
        sequence(
            job("processing"),
            job("failed", retryable=True, attempt=1),
            job("queued", retryable=False, attempt=2),
            job("processing", attempt=2),
            job("ready", attempt=2),
        )
    )
    assert final["status"] == "ready"
    assert final["attempt_count"] == 2


def test_a_failure_that_cannot_be_retried_is_final_at_once():
    calls = []

    def fetch():
        calls.append(1)
        return job("failed", retryable=False)

    assert wait(fetch)["status"] == "failed"
    assert len(calls) == 1


def test_a_failure_with_its_retries_exhausted_is_final():
    final = wait(
        sequence(
            job("failed", retryable=True, attempt=1),
            job("processing", attempt=2),
            job("failed", retryable=True, attempt=3, maximum=3),
        )
    )
    assert final["status"] == "failed"
    assert final["attempt_count"] == 3


def test_a_broken_worker_cannot_hang_the_wait():
    # A retry that never comes: bounded, and not reported as a failed job.
    with pytest.raises(JobNotSettled) as caught:
        wait(lambda: job("failed", retryable=True), timeout=0.05)
    assert retry_pending(caught.value.job) is True


def test_a_job_that_never_settles_fails_the_wait_at_the_timeout():
    with pytest.raises(JobNotSettled) as caught:
        wait(lambda: job("processing"), timeout=0.05)
    assert caught.value.job["status"] == "processing"


def test_two_reads_can_describe_a_state_the_job_was_never_in():
    # The C23 gate failure: the first read saw failed on attempt 1, the second
    # saw attempt 2 after the retry pass had set queued. No row was failed on 2.
    rows = [job("failed", retryable=True, attempt=1), job("queued", attempt=2), job("ready", attempt=2)]

    read = sequence(*rows)
    assert read()["status"] in ("ready", "failed") and read()["attempt_count"] == 2

    read = sequence(*rows)
    assert [attempt_finished(read(), 2) for _ in rows] == [False, False, True]


@pytest.mark.parametrize("status", ["queued", "processing", "extracted", "chunked", "indexed"])
def test_an_attempt_still_running_has_not_finished(status):
    assert attempt_finished(job(status, attempt=2), 2) is False


def test_a_real_failure_on_the_attempt_still_ends_the_wait():
    # So the caller's assert reports it, rather than the wait hiding it.
    assert attempt_finished(job("failed", attempt=2), 2) is True


def test_idle_waits_until_nothing_is_left_to_run():
    remaining = [["a", "b"], ["b"], []]
    wait_until_idle(lambda: remaining.pop(0), 5.0, interval=0)
    assert remaining == []


def test_work_that_never_finishes_fails_the_idle_wait_and_names_it():
    with pytest.raises(AssertionError, match="stuck-job"):
        wait_until_idle(lambda: ["stuck-job"], 0.05, interval=0)


def test_no_boundary_condition_reads_a_job_twice():
    boundary = Path(__file__).resolve().parents[1] / "boundary"
    twice = re.compile(r"lambda:.*job_row\(.*job_row\(")
    assert not [path.name for path in boundary.glob("*.py") if twice.search(path.read_text("utf-8"))]


@pytest.mark.parametrize(
    "state,pending",
    [
        (job("failed", retryable=True, attempt=1), True),
        (job("failed", retryable=True, attempt=3), False),
        (job("failed", retryable=False, attempt=1), False),
        (job("ready"), False),
        (job("processing", retryable=True), False),
    ],
)
def test_retry_pending(state, pending):
    assert retry_pending(state) is pending
