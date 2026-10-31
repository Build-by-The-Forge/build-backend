"""The boundary suite's wait: a failure with a retry due isn't the job's outcome."""

import pytest

from boundary.job_status import retry_pending, wait_until_settled

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
    # A retry that never comes: bounded, and the job is returned as it stands.
    final = wait(lambda: job("failed", retryable=True), timeout=0.05)
    assert final["status"] == "failed"
    assert retry_pending(final) is True


def test_a_job_that_never_settles_is_returned_at_the_timeout():
    assert wait(lambda: job("processing"), timeout=0.05)["status"] == "processing"


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
