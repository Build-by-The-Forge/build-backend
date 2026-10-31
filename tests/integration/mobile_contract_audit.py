"""What the running backend does against the mobile contract (M2).

Produces findings as plain strings, "<check> <METHOD> <path>[ <detail>]". The
drift test compares them with contracts/mobile/gaps.yaml. Static checks read
the real routes; probes send real authenticated HTTP requests as a student.
"""

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "contracts" / "mobile" / "openapi.yaml"
METHODS = ("get", "put", "post", "patch", "delete")
# Must never reach a student, at any depth of a response.
INTERNAL_FIELDS = {
    "storage_uri",
    "storage_key",
    "created_by_email",
    "external_task_id",
    "attempt_history",
    "error_details",
    "chunk_id",
    "correct_option",
    "correct_answer",
    "answer_key",
    "explanation",
    "context",
    "trust_policy",
    "tenant_id",
    "user_id",
}


def load_spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def contract_operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method.upper(), path, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in METHODS
    ]


def served_operations() -> dict[tuple[str, str], dict[str, Any]]:
    """Every operation the app serves, from the OpenAPI it generates itself.
    app.openapi() works with the docs routes switched off."""
    return {
        (method.upper(), path): operation
        for path, item in app.openapi()["paths"].items()
        for method, operation in item.items()
        if method in METHODS
    }


def _parameter_names(spec: dict[str, Any], operation: dict[str, Any], place: str) -> set[str]:
    names = set()
    for parameter in operation.get("parameters", []):
        if "$ref" in parameter:
            parameter = spec["components"]["parameters"][parameter["$ref"].rsplit("/", 1)[-1]]
        if parameter["in"] == place:
            names.add(parameter["name"])
    return names


def _served(served, method: str, path: str) -> tuple[dict[str, Any] | None, bool]:
    """The served operation, and whether it differs only by a trailing slash."""
    if (method, path) in served:
        return served[(method, path)], False
    slashed = (method, f"{path}/")
    return served.get(slashed), slashed in served


def static_findings(spec: dict[str, Any]) -> set[str]:
    served = served_operations()
    findings: set[str] = set()
    for method, path, operation in contract_operations(spec):
        where = f"{method} {path}"
        actual, slash = _served(served, method, path)
        if actual is None:
            findings.add(f"missing_route {where}")
            continue
        if slash:
            findings.add(f"trailing_slash {where}")
        parameters = actual.get("parameters", [])
        served_query = {p["name"] for p in parameters if p["in"] == "query"}
        for name in sorted(_parameter_names(spec, operation, "query") - served_query):
            findings.add(f"missing_query_parameter {where} {name}")
        served_headers = {p["name"].lower() for p in parameters if p["in"] == "header"}
        declared_headers = {n.lower() for n in _parameter_names(spec, operation, "header")} - {"x-tenant-slug", "range"}
        for name in sorted(declared_headers - served_headers):
            findings.add(f"missing_header {where} {name}")
        if "requestBody" in operation and "application/json" in operation["requestBody"]["content"]:
            schema = actual.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            if "$ref" not in schema:
                findings.add(f"untyped_body {where}")
    return findings


def _concrete(path: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), str(uuid4())), path)


def _fields(node: Any) -> set[str]:
    if isinstance(node, dict):
        names = set(node)
        for value in node.values():
            names |= _fields(value)
        return names
    if isinstance(node, list):
        return set().union(*(_fields(item) for item in node)) if node else set()
    return set()


def _envelope_problem(response) -> str | None:
    """None when the body has the contract's envelope for its status."""
    try:
        body = response.json()
    except ValueError:
        return "not_json"
    if not isinstance(body, dict) or not {"success", "data", "error", "meta"} <= set(body):
        return "keys"
    if not isinstance(body["meta"], dict) or "request_id" not in body["meta"]:
        return "request_id"
    if response.status_code >= 400:
        error = body["error"]
        if body["success"] is not False or body["data"] is not None or not isinstance(error, dict) or "code" not in error:
            return "error_shape"
    elif body["success"] is not True or body["error"] is not None:
        return "success_shape"
    return None


def _send(client, method: str, path: str, headers: dict[str, str], operation: dict[str, Any], values: dict[str, Any]):
    kwargs: dict[str, Any] = {"headers": headers}
    body = values.get("bodies", {}).get(operation["operationId"])
    if body is not None:
        kwargs["json"] = body
    return client.request(method, path, **kwargs)


def probe_findings(client, spec: dict[str, Any], student: dict[str, str], values: dict[str, Any]) -> set[str]:
    """Each served contract route, three ways: no token, no tenant header, and
    as the student with the given IDs."""
    served = served_operations()
    findings: set[str] = set()
    public = {o["operationId"] for _, _, o in contract_operations(spec) if o.get("security") == []}
    skip = set(values.get("skip", ()))
    everything = contract_operations(spec)
    reads = [o for o in everything if o[0] == "GET"]
    writes = [o for o in everything if o[0] != "GET"]
    # Reads run again after the writes, so a result can be seen once submitted.
    for method, path, operation in [*reads, *writes, *reads]:
        operation_id = operation["operationId"]
        where = f"{method} {path}"
        actual, _ = _served(served, method, path)
        if actual is None or operation_id in skip:
            continue
        url = _concrete(path, values["ids"])
        if operation_id not in public:
            anonymous = client.request(method, url)
            if anonymous.status_code != 401:
                findings.add(f"anonymous_not_refused {where} {anonymous.status_code}")
            problem = _envelope_problem(anonymous)
            if problem:
                findings.add(f"error_envelope {where} {problem}")
        tenant_scoped = not path.startswith(("/identity/", "/tenants/", "/invitations/"))
        if tenant_scoped:
            no_tenant = client.request(method, url, headers={"Authorization": student["Authorization"]})
            if no_tenant.status_code != 400:
                findings.add(f"tenant_header_not_required {where} {no_tenant.status_code}")
        response = _send(client, method, url, student, operation, values)
        if response.status_code == 403:
            findings.add(f"student_refused {where}")
        if response.status_code >= 500:
            findings.add(f"server_error {where} {response.status_code}")
        problem = _envelope_problem(response)
        if problem:
            findings.add(f"{'error' if response.status_code >= 400 else 'success'}_envelope {where} {problem}")
        if response.status_code < 400 and "application/json" in response.headers.get("content-type", ""):
            for name in sorted(_fields(response.json()) & INTERNAL_FIELDS):
                findings.add(f"exposes_field {where} {name}")
    return findings


def global_findings(client) -> set[str]:
    """Rules about the API as a whole, each tried once with a real request."""
    findings: set[str] = set()
    secret = 987654321
    invalid = client.post("/identity/users", json={"email": "not-checked@example.com", "password": secret})
    if str(secret) in invalid.text:
        findings.add("echoes_input POST /identity/users")
    malformed = "x" * 200 + "!"
    traced = client.get("/health/live", headers={"X-Request-ID": malformed})
    if traced.headers.get("x-request-id") == malformed:
        findings.add("request_id_unvalidated GET /health/live")
    return findings
