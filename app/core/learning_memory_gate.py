"""The learning-memory production gate (docs/assessment-lifecycle-plan.md, L0).

No student's memory is read or written in production until the gate's
conditions are met: retention, expiry, deletion, student controls, idempotency.
GATE_OPEN records that decision, and opening it takes a reviewed code change.

APP_ENVIRONMENT is an ordinary variable, so it can't alone separate test from
production: the Dockerfile's production stage bakes in a marker, and an image
with the marker refuses even when misconfigured as development. This is a
release control, not access control: an image built from another stage, or the
source run directly, has no marker.

ai-service enforces the same rule on its own side (its
app/core/learning_memory_gate.py). The backend's job is to send nothing at all.

Imports nothing from the application, since app.core.config depends on it.
"""

from pathlib import Path

GATE_OPEN = False

PRODUCTION_IMAGE_MARKER = Path("/opt/build-backend/production-image")
ENVIRONMENTS_OUTSIDE_THE_GATE = frozenset({"development", "testing"})


def memory_allowed(requested: bool, environment: str) -> bool:
    if not requested:
        return False
    if GATE_OPEN:
        return True
    # A marker that can't be examined raises, which fails closed.
    return environment in ENVIRONMENTS_OUTSIDE_THE_GATE and not PRODUCTION_IMAGE_MARKER.exists()
