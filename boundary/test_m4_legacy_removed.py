"""M4: AI-service has no user-facing identity or exam surface left.

AI-service authenticates services only; the backend owns users, tenants,
memberships and the CBT lifecycle (plan §6.2, §6.3).
"""

import pytest

SYSTEM_PATHS = {"/", "/metrics", "/api/v1/health/", "/api/v1/system/health", "/api/v1/system/ready"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/auth/login"),
        ("POST", "/auth/refresh"),
        ("GET", "/auth/me"),
        ("POST", "/auth/logout"),
        ("GET", "/exams/"),
        ("POST", "/api/v1/exams/"),
        ("POST", "/api/v1/ai/exam/start"),
        ("POST", "/api/v1/ai/exam/submit"),
        ("POST", "/api/v1/api/v1/generate"),
        ("GET", "/api/v1/ws/exam/s1"),
    ],
)
def test_no_legacy_identity_or_exam_route_answers(ai, method, path):
    assert ai.request(method, path, json={} if method == "POST" else None).status_code == 404


def test_every_ai_service_route_is_signed_or_a_system_probe(ai):
    paths = set(ai.get("/openapi.json").json()["paths"])
    unsigned = {p for p in paths if not p.startswith(("/v1/ai/", "/v1/ingest/"))}
    assert unsigned <= SYSTEM_PATHS, unsigned
