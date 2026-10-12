import pytest

from app.application.identity.ports.counter_store import CounterStoreUnavailable
from app.application.identity.throttle import (
    ACCOUNT_LOCK_SECONDS,
    AI_QUESTION_GENERATION_PER_USER,
    AI_REQUESTS_PER_USER,
    LOGIN_FAILURES_PER_ACCOUNT,
    LOGIN_FAILURES_PER_PAIR,
    PAIR_LOCK_SECONDS,
    AuthThrottle,
)
from app.core.exceptions import AppError, RateLimitedError
from app.infrastructure.ratelimit.memory_counter_store import InMemoryCounterStore

EMAIL = "victim@example.com"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def throttle(clock):
    return AuthThrottle(InMemoryCounterStore(clock))


async def fail(throttle, times, email=EMAIL, ip="10.0.0.1"):
    for _ in range(times):
        attempt = await throttle.before_login(email, ip)
        await throttle.login_failed(attempt)


async def test_pair_is_locked_after_repeated_failures_until_the_lock_expires(throttle, clock):
    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit)

    with pytest.raises(RateLimitedError) as exc:
        await throttle.before_login(EMAIL, "10.0.0.1")
    assert exc.value.retry_after == PAIR_LOCK_SECONDS

    clock.now += PAIR_LOCK_SECONDS
    await throttle.before_login(EMAIL, "10.0.0.1")


async def test_pair_lock_does_not_block_the_same_email_from_another_ip(throttle):
    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit, ip="203.0.113.9")

    await throttle.before_login(EMAIL, "10.0.0.1")  # the owner, elsewhere


async def test_pair_lock_does_not_affect_other_accounts_on_the_same_ip(throttle):
    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit)

    await throttle.before_login("someone-else@example.com", "10.0.0.1")


async def test_account_lock_after_failures_from_many_ips(throttle, clock):
    for i in range(LOGIN_FAILURES_PER_ACCOUNT.limit):
        await fail(throttle, 1, ip=f"198.51.100.{i}")

    with pytest.raises(RateLimitedError):
        await throttle.before_login(EMAIL, "10.0.0.1")
    await throttle.before_login("other@example.com", "10.0.0.1")

    clock.now += ACCOUNT_LOCK_SECONDS
    await throttle.before_login(EMAIL, "10.0.0.1")


async def test_success_resets_the_failure_counters(throttle):
    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit - 1)
    await throttle.login_succeeded(EMAIL, "10.0.0.1")

    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit - 1)

    await throttle.before_login(EMAIL, "10.0.0.1")


async def test_password_reset_lifts_the_account_lock(throttle):
    for i in range(LOGIN_FAILURES_PER_ACCOUNT.limit):
        await fail(throttle, 1, ip=f"198.51.100.{i}")

    await throttle.password_reset_completed(EMAIL, "10.0.0.1")

    await throttle.before_login(EMAIL, "10.0.0.1")


async def test_email_keys_are_case_and_space_insensitive(throttle):
    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit, email="  Victim@Example.COM ")

    with pytest.raises(RateLimitedError):
        await throttle.before_login(EMAIL, "10.0.0.1")


async def test_a_concurrent_burst_admits_only_the_limit(throttle):
    import asyncio

    async def guess():
        try:
            await throttle.before_login(EMAIL, "10.0.0.1")
            return "admitted"
        except RateLimitedError:
            return "429"

    results = await asyncio.gather(*[guess() for _ in range(30)])

    assert results.count("admitted") == LOGIN_FAILURES_PER_PAIR.limit


async def test_keys_do_not_contain_raw_emails_or_ips(throttle):
    await fail(throttle, 1)

    keys = " ".join(throttle.store._entries)
    assert EMAIL not in keys and "10.0.0.1" not in keys


async def test_unavailable_store_in_closed_mode_becomes_a_503():
    class Closed:
        async def hit(self, *args):
            raise CounterStoreUnavailable()

    with pytest.raises(AppError) as exc:
        await AuthThrottle(Closed()).register("10.0.0.1")

    assert exc.value.status_code == 503


async def test_an_expired_lock_does_not_immediately_re_lock(throttle, clock):
    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit)
    clock.now += PAIR_LOCK_SECONDS

    await fail(throttle, LOGIN_FAILURES_PER_PAIR.limit - 1)

    await throttle.before_login(EMAIL, "10.0.0.1")


async def test_ai_requests_are_limited_per_user(throttle, clock):
    for _ in range(AI_REQUESTS_PER_USER.limit):
        await throttle.ai_request("user-1")
    with pytest.raises(RateLimitedError):
        await throttle.ai_request("user-1")

    await throttle.ai_request("user-2")  # another user is unaffected
    clock.now += AI_REQUESTS_PER_USER.window_seconds
    await throttle.ai_request("user-1")


async def test_question_generation_has_its_own_lower_limit(throttle):
    for _ in range(AI_QUESTION_GENERATION_PER_USER.limit):
        await throttle.ai_question_generation("user-1")
    with pytest.raises(RateLimitedError):
        await throttle.ai_question_generation("user-1")
    await throttle.ai_request("user-1")  # chat still has headroom


async def test_question_generation_counts_towards_the_ai_limit(throttle):
    for _ in range(AI_REQUESTS_PER_USER.limit - 1):
        await throttle.ai_request("user-1")
    await throttle.ai_question_generation("user-1")
    with pytest.raises(RateLimitedError):
        await throttle.ai_request("user-1")
