"""C11: with Redis stopped, signed requests fail closed (503), nothing runs.

Selected only by scripts/m3_boundary_gate.sh after it stops the redis
service (marker ``redis_down``); the rest of the suite runs with Redis up.
"""

import uuid

import pytest

from boundary.conftest import CALLBACK_PATH, jbytes, system_context, to_ai, to_backend, user_context

pytestmark = pytest.mark.redis_down


def test_c11_ai_service_refuses_with_503_when_its_replay_store_is_down(ai):
    raw = jbytes({"message": "hello"})
    context = user_context(str(uuid.uuid4()), str(uuid.uuid4()), ["ai.use"])
    response = ai.post("/v1/ai/chat", content=raw, headers=to_ai("POST", "/v1/ai/chat", raw, context))
    assert response.status_code == 503


def test_c11_the_backend_refuses_callbacks_with_503_when_its_replay_store_is_down(backend):
    job = {
        "job_id": str(uuid.uuid4()),
        "event_id": str(uuid.uuid4()),
        "event_type": "job_failed",
        "external_task_id": "task_x",
        "run_number": 1,
        "attempt_count": 1,
        "error_code": "X",
        "error_message": "x",
        "is_retryable": False,
    }
    raw = jbytes(job)
    response = backend.post(CALLBACK_PATH, content=raw, headers=to_backend(CALLBACK_PATH, raw, system_context(str(uuid.uuid4()))))
    assert response.status_code == 503


def test_c11_an_unsigned_request_is_still_401_not_503(ai):
    assert ai.post("/v1/ai/chat", json={"message": "x"}).status_code == 401
