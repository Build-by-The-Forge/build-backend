"""Registration answers before its slow work, over a real socket against PostgreSQL.

The precise comparison is scripts/measure_registration_timing.py, run by hand: timing
is too noisy on shared runners to gate on a few milliseconds. What this holds in CI can't
be noise: a response that waited for a one-second email would take over a second.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMAIL_DELAY_MS = 1000


def test_a_new_account_is_answered_before_its_email_and_the_answers_match():
    # Its own process: the server needs its own event loop and database pool.
    run = subprocess.run(
        [
            sys.executable,
            "scripts/measure_registration_timing.py",
            "--samples",
            "20",
            "--email-delay",
            "1",
            "--sustained-samples",
            "5",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[-2000:]
    result = json.loads(run.stdout)

    assert result["distinct_answers"] == 1
    assert result["new"]["p50_ms"] < EMAIL_DELAY_MS
    assert result["existing"]["p50_ms"] < EMAIL_DELAY_MS
    assert result["follow_up_after_new"]["p50_ms"] < EMAIL_DELAY_MS
