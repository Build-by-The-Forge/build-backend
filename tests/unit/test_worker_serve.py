"""The worker starts every loop it should, each with a well-formed call.

A merge once spliced two loop registrations into one call: the worker
crashed at startup with "_run_loop() takes 5 positional arguments", which
only the boundary gate caught. This starts serve() with _run_loop replaced
by a stand-in of the same signature, so a malformed registration fails here.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.worker as worker

EXPECTED_LOOPS = {
    "dispatch",
    "retry",
    "orphan_sweep",
    "recoverer",
    "scans",
    "scope_assignments",
    "attempt_finalizer",
}


@pytest.mark.asyncio
async def test_serve_starts_every_loop_with_a_well_formed_call(monkeypatch):
    started: list[str] = []

    async def run_loop(name, interval_seconds, run_pass, stop, completed_at):
        # The real signature: a call with the wrong arguments raises TypeError.
        assert callable(run_pass) and interval_seconds >= 1
        started.append(name)
        stop.set()

    server = MagicMock()
    monkeypatch.setattr(worker, "_run_loop", run_loop)
    monkeypatch.setattr(worker, "start_http_server", lambda *args, **kwargs: (server, None))
    monkeypatch.setattr(worker, "write_health_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "engine", MagicMock(dispose=AsyncMock()))

    await worker.serve()

    assert set(started) == EXPECTED_LOOPS
    assert len(started) == len(EXPECTED_LOOPS)  # each started once
