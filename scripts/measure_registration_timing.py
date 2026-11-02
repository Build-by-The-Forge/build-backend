"""How long POST /identity/users takes for a new and for an existing email.

Real uvicorn, real HTTP over a socket, the real Argon2 hasher, and whatever database
POSTGRES_URL names. The per-IP limit is lifted, because it exists to stop exactly this.
New and existing requests are shuffled together, so drift affects both alike. Each uses
its own email, and a warm-up is discarded.

The email sender is replaced by one that takes --email-delay seconds. A response that
waited for it would show up as a difference of at least that much.

Three comparisons. new vs existing is the channel itself. The noise floor compares two
random halves of the existing samples, so it's what a difference of nothing looks like.
The follow-up compares a health check sent straight after each registration, because a
new account's work continues after its answer and could slow whatever comes next. The
sustained probe keeps checking through the jitter window and keeps the slowest answer,
which is what someone looking for that work would try.

    python scripts/measure_registration_timing.py --samples 300 --email-delay 0.5

Prints JSON. It can't prove there's no channel: it measures one machine, and a patient
attacker averages across many requests. The per-IP limit is what bounds that.
"""

import argparse
import asyncio
import json
import random
import socket
import statistics
import threading
import time
from uuid import uuid4

import httpx
import uvicorn

PASSWORD = "Correct-Horse-Battery-9"
WARM_UP = 20
BOOTSTRAP_ROUNDS = 2000
PROBE_WINDOW_SECONDS = 1.2


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _start_server(email_delay: float) -> tuple[uvicorn.Server, str]:
    from app.api import identity
    from app.main import app

    async def unlimited(_ip: str) -> None:
        return None

    async def slow_send(_message: object) -> None:
        await asyncio.sleep(email_delay)

    identity.throttle.register = unlimited  # type: ignore[method-assign]
    identity.service.email_sender.send = slow_send  # type: ignore[method-assign]

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}"


def _summary(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    at = lambda share: ordered[min(int(len(ordered) * share), len(ordered) - 1)]  # noqa: E731
    return {
        "n": len(ordered),
        "min_ms": round(ordered[0] * 1000, 2),
        "p10_ms": round(at(0.10) * 1000, 2),
        "p50_ms": round(statistics.median(ordered) * 1000, 2),
        "p90_ms": round(at(0.90) * 1000, 2),
        "p99_ms": round(at(0.99) * 1000, 2),
        "max_ms": round(ordered[-1] * 1000, 2),
        "mean_ms": round(statistics.fmean(ordered) * 1000, 2),
        "stdev_ms": round(statistics.stdev(ordered) * 1000, 2),
    }


def _median_difference_interval(new: list[float], existing: list[float], rng: random.Random) -> list[float]:
    """A bootstrap 95% interval for median(new) - median(existing), in milliseconds."""
    differences = sorted(
        statistics.median(rng.choices(new, k=len(new))) - statistics.median(rng.choices(existing, k=len(existing)))
        for _ in range(BOOTSTRAP_ROUNDS)
    )
    low, high = differences[int(BOOTSTRAP_ROUNDS * 0.025)], differences[int(BOOTSTRAP_ROUNDS * 0.975)]
    return [round(low * 1000, 2), round(high * 1000, 2)]


def measure(samples: int, email_delay: float, seed: int, sustained_samples: int) -> dict[str, object]:
    from app.core.config import settings

    rng = random.Random(seed)
    server, base_url = _start_server(email_delay)
    try:
        with httpx.Client(base_url=base_url, timeout=30) as client:

            def register(email: str) -> tuple[float, httpx.Response]:
                started = time.perf_counter()
                response = client.post("/identity/users", json={"email": email, "password": PASSWORD})
                return time.perf_counter() - started, response

            existing_emails = [f"timing-{uuid4().hex}@example.com" for _ in range(samples + WARM_UP)]
            for email in existing_emails:
                assert register(email)[1].status_code == 202
            # Their accounts are created after their answers: "existing" must be true.
            time.sleep(settings.registration_completion_jitter_seconds + email_delay + 2)

            plan = ["new"] * (samples + WARM_UP) + ["existing"] * (samples + WARM_UP)
            rng.shuffle(plan)
            remaining = list(existing_emails)
            timings: dict[str, list[float]] = {"new": [], "existing": []}
            follow_ups: dict[str, list[float]] = {"new": [], "existing": []}
            sustained: dict[str, list[float]] = {"new": [], "existing": []}
            answers: set[tuple[int, bytes]] = set()
            for kind in plan:
                email = f"timing-{uuid4().hex}@example.com" if kind == "new" else remaining.pop()
                elapsed, response = register(email)
                answers.add((response.status_code, response.content))
                timings[kind].append(elapsed)
                started = time.perf_counter()
                client.get("/health/live")
                follow_ups[kind].append(time.perf_counter() - started)
                if len(sustained[kind]) < sustained_samples:
                    slowest = 0.0
                    window_ends = time.perf_counter() + PROBE_WINDOW_SECONDS
                    while time.perf_counter() < window_ends:
                        started = time.perf_counter()
                        client.get("/health/live")
                        slowest = max(slowest, time.perf_counter() - started)
                    sustained[kind].append(slowest)
    finally:
        server.should_exit = True

    new, existing = timings["new"][WARM_UP:], timings["existing"][WARM_UP:]
    next_new, next_existing = follow_ups["new"][WARM_UP:], follow_ups["existing"][WARM_UP:]
    shuffled = rng.sample(existing, k=len(existing))
    half_a, half_b = shuffled[: len(shuffled) // 2], shuffled[len(shuffled) // 2 :]
    return {
        "samples_per_kind": samples,
        "warm_up_discarded": WARM_UP,
        "email_delay_ms": round(email_delay * 1000),
        "completion_jitter_seconds": settings.registration_completion_jitter_seconds,
        "seed": seed,
        "new": _summary(new),
        "existing": _summary(existing),
        "median_difference_ms": round((statistics.median(new) - statistics.median(existing)) * 1000, 2),
        "median_difference_95_ci_ms": _median_difference_interval(new, existing, rng),
        "noise_floor_median_difference_ms": round((statistics.median(half_a) - statistics.median(half_b)) * 1000, 2),
        "noise_floor_95_ci_ms": _median_difference_interval(half_a, half_b, rng),
        "follow_up_after_new": _summary(next_new),
        "follow_up_after_existing": _summary(next_existing),
        "follow_up_median_difference_ms": round((statistics.median(next_new) - statistics.median(next_existing)) * 1000, 2),
        "follow_up_median_difference_95_ci_ms": _median_difference_interval(next_new, next_existing, rng),
        "sustained_probe_after_new": _summary(sustained["new"]),
        "sustained_probe_after_existing": _summary(sustained["existing"]),
        "sustained_median_difference_ms": round(
            (statistics.median(sustained["new"]) - statistics.median(sustained["existing"])) * 1000, 2
        ),
        "sustained_median_difference_95_ci_ms": _median_difference_interval(sustained["new"], sustained["existing"], rng),
        "distinct_answers": len(answers),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--email-delay", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--sustained-samples", type=int, default=100)
    options = parser.parse_args()
    print(json.dumps(measure(options.samples, options.email_delay, options.seed, options.sustained_samples), indent=1))


if __name__ == "__main__":
    main()
