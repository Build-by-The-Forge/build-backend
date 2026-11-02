"""How long POST /identity/users takes for a new and for an existing email, and whether
anything a caller can reach behaves differently afterwards.

Four processes, as deployed: uvicorn over a real socket, the registration worker, a stall
detector and this client, with the real Argon2 hasher and whatever database POSTGRES_URL
names. The per-IP limit is lifted, because it exists to stop exactly this. New and existing
requests are shuffled together so drift affects both alike, each uses its own email, and a
warm-up is discarded.

The comparisons:

- new vs existing: the channel itself.
- noise floor: two random halves of the existing samples, so what no difference looks like.
- follow-up: a health check sent straight after each registration.
- sustained: for each of the first registrations, probing a route without the database and
  one with it, for longer than the worker's interval, keeping the slowest of each. That's
  what someone looking for the worker's writes would try, and the database is the only
  thing the worker and a request still share.

Outliers: answers over three times their kind's median, each checked against the stall
detector, a separate process that notices when it isn't scheduled on time. An outlier
overlapping a stall happened while the whole machine was held up.

    python scripts/measure_registration_timing.py --samples 300

Prints JSON. It can't prove there's no channel: it measures one machine.
"""

import argparse
import asyncio
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

PASSWORD = "Correct-Horse-Battery-9"
WARM_UP = 20
BOOTSTRAP_ROUNDS = 2000
PROBE_WINDOW_SECONDS = 1.5
STALL_TICK_SECONDS = 0.005
STALL_REPORTED_SECONDS = 0.05


def _replace_email(identity, email_delay: float) -> None:
    async def slow_send(_message: object) -> None:
        await asyncio.sleep(email_delay)

    identity.service.email_sender.send = slow_send


def _run_server(port: int, email_delay: float) -> None:
    import uvicorn

    from app.api import identity
    from app.main import app

    async def unlimited(_ip: str) -> None:
        return None

    identity.throttle.register = unlimited
    _replace_email(identity, email_delay)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")


def _run_worker(email_delay: float) -> None:
    from app.api import identity
    from app.core.config import settings

    _replace_email(identity, email_delay)

    async def forever() -> None:
        while True:
            await identity.service.process_pending_registrations()
            await asyncio.sleep(settings.worker_registration_interval_seconds)

    asyncio.run(forever())


def _run_stall_detector() -> None:
    """Prints [started_at, seconds] per stall when told to stop by closing its stdin."""
    import threading

    stalls: list[list[float]] = []
    done = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.read(), done.set()), daemon=True).start()
    while not done.is_set():
        before = time.time()
        time.sleep(STALL_TICK_SECONDS)
        late = time.time() - before - STALL_TICK_SECONDS
        if late > STALL_REPORTED_SECONDS:
            stalls.append([before, late])
    print(json.dumps(stalls))


def _spawn(role: str, *arguments: str, **options) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.Popen([sys.executable, __file__, "--role", role, *arguments], cwd=ROOT, env=env, **options)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def _pending_count() -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(settings.effective_postgres_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text("select count(*) from pending_registrations"))).scalar_one()
    finally:
        await engine.dispose()


def _wait_until_processed(timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while asyncio.run(_pending_count()) > 0:
        if time.monotonic() > deadline:
            raise TimeoutError("the worker didn't finish the seeded registrations")
        time.sleep(0.5)


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


def _compare(first: list[float], second: list[float], rng: random.Random) -> dict[str, object]:
    """Median difference, with a bootstrap 95% interval, in milliseconds."""
    differences = sorted(
        statistics.median(rng.choices(first, k=len(first))) - statistics.median(rng.choices(second, k=len(second)))
        for _ in range(BOOTSTRAP_ROUNDS)
    )
    low, high = differences[int(BOOTSTRAP_ROUNDS * 0.025)], differences[int(BOOTSTRAP_ROUNDS * 0.975)]
    return {
        "difference_ms": round((statistics.median(first) - statistics.median(second)) * 1000, 2),
        "interval_95_ms": [round(low * 1000, 2), round(high * 1000, 2)],
    }


def _outliers(kind: str, spans: list[tuple[float, float]], stalls: list[list[float]]) -> list[dict[str, object]]:
    median = statistics.median(end - start for start, end in spans)
    found = []
    for position, (start, end) in enumerate(spans):
        if end - start > median * 3:
            overlapping = [stall for stall in stalls if stall[0] < end and stall[0] + stall[1] > start]
            found.append(
                {
                    "kind": kind,
                    "position": position,
                    "ms": round((end - start) * 1000, 1),
                    "started_at_utc": datetime.fromtimestamp(start, timezone.utc).strftime("%H:%M:%S.%f")[:-3],
                    "stalled_ms": round(sum(stall[1] for stall in overlapping) * 1000, 1),
                }
            )
    return found


def measure(samples: int, email_delay: float, seed: int, sustained_samples: int) -> dict[str, object]:
    rng = random.Random(seed)
    port = _free_port()
    detector = _spawn("stalls", stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    server = _spawn("server", "--port", str(port), "--email-delay", str(email_delay))
    worker = _spawn("worker", "--email-delay", str(email_delay))
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60) as client:
            for _ in range(120):
                try:
                    if client.get("/health/live").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)

            def register(email: str) -> tuple[float, float, httpx.Response]:
                started = time.time()
                response = client.post("/identity/users", json={"email": email, "password": PASSWORD})
                return started, time.time(), response

            probe_email = f"timing-probe-{uuid4().hex}@example.com"
            existing_emails = [f"timing-{uuid4().hex}@example.com" for _ in range(samples + WARM_UP)]
            for email in [probe_email, *existing_emails]:
                assert register(email)[2].status_code == 202
            # "Existing" must be true by now: the worker creates them after their answers.
            _wait_until_processed(timeout=120 + (samples + WARM_UP) * email_delay * 2)
            signed_in = client.post("/identity/authenticate", json={"email": probe_email, "password": PASSWORD})
            assert signed_in.status_code == 200, signed_in.text
            bearer = {"Authorization": f"Bearer {signed_in.json()['data']['access_token']}"}

            plan = ["new"] * (samples + WARM_UP) + ["existing"] * (samples + WARM_UP)
            rng.shuffle(plan)
            remaining = list(existing_emails)
            spans: dict[str, list[tuple[float, float]]] = {"new": [], "existing": []}
            follow_ups: dict[str, list[float]] = {"new": [], "existing": []}
            without_database: dict[str, list[float]] = {"new": [], "existing": []}
            with_database: dict[str, list[float]] = {"new": [], "existing": []}
            answers: set[tuple[int, bytes]] = set()
            for kind in plan:
                email = f"timing-{uuid4().hex}@example.com" if kind == "new" else remaining.pop()
                started, ended, response = register(email)
                answers.add((response.status_code, response.content))
                spans[kind].append((started, ended))
                before = time.perf_counter()
                client.get("/health/live")
                follow_ups[kind].append(time.perf_counter() - before)
                if len(with_database[kind]) < sustained_samples:
                    slowest_plain, slowest_database = 0.0, 0.0
                    window_ends = time.perf_counter() + PROBE_WINDOW_SECONDS
                    while time.perf_counter() < window_ends:
                        before = time.perf_counter()
                        client.get("/health/live")
                        middle = time.perf_counter()
                        client.get("/identity/me", headers=bearer)
                        after = time.perf_counter()
                        slowest_plain = max(slowest_plain, middle - before)
                        slowest_database = max(slowest_database, after - middle)
                    without_database[kind].append(slowest_plain)
                    with_database[kind].append(slowest_database)
            # Nothing left behind, including the password hashes in unprocessed rows.
            _wait_until_processed(timeout=120 + (samples + WARM_UP) * email_delay * 2)
    finally:
        server.terminate()
        worker.terminate()
        stall_output, _ = detector.communicate("", timeout=30)
    stalls = json.loads(stall_output)

    kept = {kind: spans[kind][WARM_UP:] for kind in spans}
    new = [end - start for start, end in kept["new"]]
    existing = [end - start for start, end in kept["existing"]]
    shuffled = rng.sample(existing, k=len(existing))
    half_a, half_b = shuffled[: len(shuffled) // 2], shuffled[len(shuffled) // 2 :]
    outliers = _outliers("new", kept["new"], stalls) + _outliers("existing", kept["existing"], stalls)
    database_probes = rng.sample(with_database["existing"], k=len(with_database["existing"]))
    probes_a, probes_b = database_probes[: len(database_probes) // 2], database_probes[len(database_probes) // 2 :]
    return {
        "samples_per_kind": samples,
        "warm_up_discarded": WARM_UP,
        "email_delay_ms": round(email_delay * 1000),
        "seed": seed,
        "new": _summary(new),
        "existing": _summary(existing),
        "answer": _compare(new, existing, rng),
        "noise_floor": _compare(half_a, half_b, rng),
        "follow_up": _compare(follow_ups["new"][WARM_UP:], follow_ups["existing"][WARM_UP:], rng),
        "follow_up_after_new": _summary(follow_ups["new"][WARM_UP:]),
        "follow_up_after_existing": _summary(follow_ups["existing"][WARM_UP:]),
        "sustained_samples_per_kind": sustained_samples,
        "sustained_without_database": _compare(without_database["new"], without_database["existing"], rng),
        "sustained_with_database": _compare(with_database["new"], with_database["existing"], rng),
        "sustained_with_database_noise_floor": _compare(probes_a, probes_b, rng),
        "sustained_with_database_after_new": _summary(with_database["new"]),
        "sustained_with_database_after_existing": _summary(with_database["existing"]),
        "distinct_answers": len(answers),
        "stalls_over_50_ms": len(stalls),
        "longest_stall_ms": round(max((stall[1] for stall in stalls), default=0) * 1000, 1),
        "outliers_over_3x_median": outliers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--email-delay", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--sustained-samples", type=int, default=100)
    parser.add_argument("--role", choices=["measure", "server", "worker", "stalls"], default="measure")
    parser.add_argument("--port", type=int, default=0)
    options = parser.parse_args()
    if options.role == "server":
        _run_server(options.port, options.email_delay)
    elif options.role == "worker":
        _run_worker(options.email_delay)
    elif options.role == "stalls":
        _run_stall_detector()
    else:
        print(json.dumps(measure(options.samples, options.email_delay, options.seed, options.sustained_samples), indent=1))


if __name__ == "__main__":
    main()
