"""Abuse controls for the public identity endpoints (M2 commit 9).

Three separate mechanisms, deliberately kept apart:

* rate limits - fixed-window request counts per IP or per email; exceeding
  one returns 429 until the window ends;
* temporary lock - after repeated failed sign-ins, password attempts for
  that email (or email + IP pair) are refused for a while; it lives only in
  the counter store and expires on its own;
* account status - users.status (LOCKED, DISABLED, ...) is an
  administrative state and is never changed by this module.

Per-IP limits are generous because many students share one campus NAT
address; brute force is stopped by the per-email counters instead. The
per-email lock is a known trade-off: someone who knows an email can delay
that user's sign-in for up to ACCOUNT_LOCK_SECONDS at a time, but a
successful password reset clears the lock, so they cannot shut the owner
out. Counters are keyed by a hash of the email whether or not an account
exists, so a 429 reveals nothing about account existence.
"""

import hashlib
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TypeVar

from app.application.identity.ports.counter_store import (
    CounterStore,
    CounterStoreUnavailable,
)
from app.core.exceptions import AppError, RateLimitedError

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    limit: int
    window_seconds: int


# Plain request limits (every attempt counts).
LOGIN_PER_IP = Rule("login:ip", 100, 15 * 60)
REGISTER_PER_IP = Rule("register:ip", 30, 60 * 60)
FORGOT_PER_IP = Rule("forgot:ip", 20, 60 * 60)
FORGOT_PER_EMAIL = Rule("forgot:email", 3, 60 * 60)
RESET_PER_IP = Rule("reset:ip", 20, 15 * 60)
VERIFY_PER_IP = Rule("verify:ip", 20, 15 * 60)
RESEND_PER_IP = Rule("resend:ip", 20, 60 * 60)
RESEND_PER_EMAIL = Rule("resend:email", 3, 60 * 60)
REFRESH_PER_IP = Rule("refresh:ip", 120, 60)
INVITATION_ACCEPT_PER_IP = Rule("invite-accept:ip", 20, 15 * 60)
INVITATION_CREATE_PER_USER = Rule("invite-create:user", 100, 60 * 60)
DOMAIN_JOIN_PER_IP = Rule("domain-join:ip", 20, 15 * 60)
# AI requests proxied to AI-service (design B.5), per user across tenants:
# each call costs model time, and question generation the most.
AI_REQUESTS_PER_USER = Rule("ai:user", 30, 60)
AI_QUESTION_GENERATION_PER_USER = Rule("ai-questions:user", 10, 60)

# Failure counters that lead to a temporary lock. Each counter's window is
# no longer than its lock, so the counter has expired by the time the lock
# does and the next attempt starts from zero instead of re-locking at once.
LOGIN_FAILURES_PER_PAIR = Rule("login-fail:pair", 5, 15 * 60)
LOGIN_FAILURES_PER_ACCOUNT = Rule("login-fail:account", 20, 15 * 60)
PASSWORD_CHANGE_FAILURES = Rule("change-fail:user", 5, 15 * 60)
PAIR_LOCK_SECONDS = 15 * 60
ACCOUNT_LOCK_SECONDS = 15 * 60
PASSWORD_CHANGE_LOCK_SECONDS = 15 * 60


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    email: str
    ip: str
    pair_count: int
    account_count: int


def _digest(value: str) -> str:
    # Keys never hold raw emails or IPs.
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _email(value: str) -> str:
    return value.strip().lower()


class AuthThrottle:
    def __init__(self, store: CounterStore, prefix: str = "auth") -> None:
        self.store = store
        self._prefix = prefix

    def _key(self, kind: str, *parts: str) -> str:
        return f"{self._prefix}:{kind}:{_digest('|'.join(parts))}"

    @staticmethod
    async def _guard(operation: Awaitable[T]) -> T:
        try:
            return await operation
        except CounterStoreUnavailable:
            raise AppError("service temporarily unavailable", status_code=503) from None

    async def _limit(self, rule: Rule, subject: str) -> None:
        count, ttl = await self._guard(self.store.hit(self._key(rule.name, subject), rule.window_seconds))
        if count > rule.limit:
            raise RateLimitedError(ttl)

    async def _refuse_if_locked(self, *lock_keys: str) -> None:
        for key in lock_keys:
            ttl = await self._guard(self.store.lock_ttl(key))
            if ttl > 0:
                raise RateLimitedError(ttl)

    # --- sign-in -----------------------------------------------------------

    def _login_keys(self, email: str, ip: str) -> dict[str, str]:
        email = _email(email)
        return {
            "pair_failures": self._key(LOGIN_FAILURES_PER_PAIR.name, email, ip),
            "account_failures": self._key(LOGIN_FAILURES_PER_ACCOUNT.name, email),
            "pair_lock": self._key("login-lock:pair", email, ip),
            "account_lock": self._key("login-lock:account", email),
        }

    async def before_login(self, email: str, ip: str) -> "LoginAttempt":
        """Admit one password attempt, or raise RateLimitedError.

        Every attempt is counted as a failure *before* the password is
        checked and the count is cleared on success. Counting first is what
        makes the limit hold under concurrency: a burst of parallel guesses
        each gets a distinct count, and only the first ``limit`` of them
        reach password verification.
        """
        await self._limit(LOGIN_PER_IP, ip)
        keys = self._login_keys(email, ip)
        await self._refuse_if_locked(keys["pair_lock"], keys["account_lock"])

        pair_count, _ = await self._guard(self.store.hit(keys["pair_failures"], LOGIN_FAILURES_PER_PAIR.window_seconds))
        account_count, _ = await self._guard(self.store.hit(keys["account_failures"], LOGIN_FAILURES_PER_ACCOUNT.window_seconds))
        attempt = LoginAttempt(email, ip, pair_count, account_count)
        if pair_count > LOGIN_FAILURES_PER_PAIR.limit:
            await self._lock_pair(keys)
            raise RateLimitedError(PAIR_LOCK_SECONDS)
        if account_count > LOGIN_FAILURES_PER_ACCOUNT.limit:
            await self._lock_account(keys)
            raise RateLimitedError(ACCOUNT_LOCK_SECONDS)
        return attempt

    async def _lock_pair(self, keys: dict[str, str]) -> None:
        await self._guard(self.store.lock(keys["pair_lock"], PAIR_LOCK_SECONDS))

    async def _lock_account(self, keys: dict[str, str]) -> None:
        await self._guard(self.store.lock(keys["account_lock"], ACCOUNT_LOCK_SECONDS))
        logger.warning("temporary sign-in lock applied to an account")

    async def login_failed(self, attempt: "LoginAttempt") -> list[str]:
        """The admitted attempt had a wrong password (already counted).

        Returns the scopes ("pair", "account") locked as a result.
        """
        keys = self._login_keys(attempt.email, attempt.ip)
        locked = []
        if attempt.pair_count >= LOGIN_FAILURES_PER_PAIR.limit:
            await self._lock_pair(keys)
            locked.append("pair")
        if attempt.account_count >= LOGIN_FAILURES_PER_ACCOUNT.limit:
            await self._lock_account(keys)
            locked.append("account")
        return locked

    async def login_succeeded(self, email: str, ip: str) -> None:
        """The password was correct (even if the account is blocked)."""
        keys = self._login_keys(email, ip)
        await self._guard(self.store.clear(keys["pair_failures"], keys["account_failures"]))

    async def password_reset_completed(self, email: str, ip: str) -> None:
        """The owner proved control of the mailbox: lift sign-in locks."""
        await self._guard(self.store.clear(*self._login_keys(email, ip).values()))

    # --- authenticated password change -------------------------------------

    def _change_keys(self, user_id: str) -> tuple[str, str]:
        return (
            self._key(PASSWORD_CHANGE_FAILURES.name, user_id),
            self._key("change-lock:user", user_id),
        )

    async def before_password_change(self, user_id: str) -> None:
        await self._refuse_if_locked(self._change_keys(user_id)[1])

    async def password_change_failed(self, user_id: str) -> None:
        failures, lock = self._change_keys(user_id)
        count, _ = await self._guard(self.store.hit(failures, PASSWORD_CHANGE_FAILURES.window_seconds))
        if count >= PASSWORD_CHANGE_FAILURES.limit:
            await self._guard(self.store.lock(lock, PASSWORD_CHANGE_LOCK_SECONDS))

    async def password_change_succeeded(self, user_id: str) -> None:
        await self._guard(self.store.clear(self._change_keys(user_id)[0]))

    # --- plain request limits ----------------------------------------------

    async def register(self, ip: str) -> None:
        await self._limit(REGISTER_PER_IP, ip)

    async def forgot_password(self, email: str, ip: str) -> None:
        await self._limit(FORGOT_PER_IP, ip)
        await self._limit(FORGOT_PER_EMAIL, _email(email))

    async def reset_password(self, ip: str) -> None:
        await self._limit(RESET_PER_IP, ip)

    async def verify_email(self, ip: str) -> None:
        await self._limit(VERIFY_PER_IP, ip)

    async def resend_verification(self, email: str, ip: str) -> None:
        await self._limit(RESEND_PER_IP, ip)
        await self._limit(RESEND_PER_EMAIL, _email(email))

    async def refresh(self, ip: str) -> None:
        await self._limit(REFRESH_PER_IP, ip)

    async def accept_invitation(self, ip: str) -> None:
        await self._limit(INVITATION_ACCEPT_PER_IP, ip)

    async def create_invitation(self, user_id: str) -> None:
        await self._limit(INVITATION_CREATE_PER_USER, user_id)

    async def domain_join(self, ip: str) -> None:
        await self._limit(DOMAIN_JOIN_PER_IP, ip)

    async def ai_request(self, user_id: str) -> None:
        await self._limit(AI_REQUESTS_PER_USER, user_id)

    async def ai_question_generation(self, user_id: str) -> None:
        await self._limit(AI_REQUESTS_PER_USER, user_id)
        await self._limit(AI_QUESTION_GENERATION_PER_USER, user_id)
