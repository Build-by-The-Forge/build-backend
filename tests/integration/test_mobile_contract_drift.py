"""The M2 drift gate: observed gaps must equal contracts/mobile/gaps.yaml.

It fails if a gap appears, changes, or disappears without proof. Closing a
gap means moving it to `closed` with a test that proves it.
"""

import copy
import hashlib

import pytest
import yaml
from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import TopicModel
from tests.integration.assessment.test_assessment_visibility import assessment_with_question
from tests.integration.mobile_contract_audit import (
    ROOT,
    SPEC_PATH,
    global_findings,
    load_spec,
    probe_findings,
    static_findings,
)

GAPS_PATH = ROOT / "contracts" / "mobile" / "gaps.yaml"
HIGHEST_GAP = 39
# Checks that mean behaviour is absent or wrong; the rest are shape differences.
IMPLEMENTATION_CHECKS = {"missing_route", "student_refused", "server_error"}


def contract_hash() -> str:
    return hashlib.sha256(SPEC_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def drift(observed: set[str], gaps: dict, *, sha256: str, proof_exists=None) -> list[str]:
    """Every way the allowlist and reality disagree."""
    problems = []
    if gaps["contract_sha256"] != sha256:
        problems.append(f"the contract changed: review the gaps, then set contract_sha256 to {sha256}")

    open_gaps = [("contract", g) for g in gaps["contract_gaps"]] + [("implementation", g) for g in gaps["implementation_gaps"]]
    allowed: dict[str, str] = {}
    for kind, gap in open_gaps:
        if not gap.get("findings") and not gap.get("evidence"):
            problems.append(f"{gap['id']} has neither findings nor evidence")
        for finding in gap.get("findings", []):
            if finding in allowed:
                problems.append(f"{finding} is under both {allowed[finding]} and {gap['id']}")
            allowed[finding] = gap["id"]
            is_implementation = finding.split()[0] in IMPLEMENTATION_CHECKS
            if is_implementation != (kind == "implementation"):
                problems.append(f"{gap['id']} is a {kind} gap but holds {finding}")

    problems += [f"new gap, not in the allowlist: {f}" for f in sorted(observed - set(allowed))]
    problems += [f"gone, so close {allowed[f]} with proof: {f}" for f in sorted(set(allowed) - observed)]

    closed = gaps.get("closed", [])
    for gap in closed:
        if not gap.get("proof"):
            problems.append(f"{gap['id']} is closed without proof")
        elif proof_exists is not None and not proof_exists(gap["proof"]):
            problems.append(f"{gap['id']}'s proof doesn't exist: {gap['proof']}")

    ids = [g["id"] for _, g in open_gaps] + [g["id"] for g in closed]
    expected = [f"G-{n:02d}" for n in range(1, HIGHEST_GAP + 1)]
    problems += [f"{i} disappeared" for i in expected if i not in ids]
    problems += [f"{i} is listed twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    problems += [f"{i} isn't a registered gap ID; raise HIGHEST_GAP" for i in sorted(set(ids) - set(expected))]
    return problems


def proof_exists(proof: str) -> bool:
    path, _, name = proof.partition("::")
    file = ROOT / path
    return file.is_file() and f"def {name}(" in file.read_text(encoding="utf-8")


def load_gaps() -> dict:
    return yaml.safe_load(GAPS_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_observed_behaviour_matches_the_gap_allowlist(client):
    spec = load_spec()
    _, student, assessment_id, _ = await assessment_with_question(client, published=True)
    assessment = client.get(f"/assessment/assessments/{assessment_id}", headers=student).json()["data"]
    attempt_id = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student).json()["data"]["id"]
    questions = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student).json()["data"]["questions"]
    async with SessionLocal() as session:
        topic_id = await session.scalar(select(TopicModel.id).where(TopicModel.course_id == assessment["course_id"]))
    values = {
        "ids": {
            "assessment_id": assessment_id,
            "attempt_id": attempt_id,
            "assessment_question_id": questions[0]["assessment_question_id"],
            "course_id": assessment["course_id"],
            "topic_id": topic_id,
        },
        "bodies": {"saveAnswer": {"selected_option_index": 0}},
        # These would end the probe's own session.
        "skip": {"logout", "logoutAll", "changePassword"},
    }

    observed = static_findings(spec) | probe_findings(client, spec, student, values) | global_findings(client)

    problems = drift(observed, load_gaps(), sha256=contract_hash(), proof_exists=proof_exists)
    assert not problems, "\n".join(problems)


GAPS = {
    "contract_sha256": "abc",
    "contract_gaps": [{"id": "G-01", "findings": ["error_envelope GET /a keys"]}],
    "implementation_gaps": [{"id": "G-02", "findings": ["missing_route GET /b"]}],
    "closed": [{"id": "G-03", "proof": "tests/x.py::test_y"}],
}
OBSERVED = {"error_envelope GET /a keys", "missing_route GET /b"}


@pytest.fixture
def three_gaps(monkeypatch):
    monkeypatch.setitem(globals(), "HIGHEST_GAP", 3)
    return copy.deepcopy(GAPS)


def test_the_gate_accepts_an_exact_match(three_gaps):
    assert drift(OBSERVED, three_gaps, sha256="abc") == []


def test_the_gate_fails_on_a_new_gap(three_gaps):
    assert any("new gap" in p for p in drift(OBSERVED | {"missing_route GET /c"}, three_gaps, sha256="abc"))


def test_the_gate_fails_when_a_gap_vanishes_without_being_closed(three_gaps):
    assert any("gone, so close G-02" in p for p in drift({"error_envelope GET /a keys"}, three_gaps, sha256="abc"))


def test_the_gate_fails_when_a_gap_is_deleted_from_the_list(three_gaps):
    three_gaps["implementation_gaps"] = []
    problems = drift({"error_envelope GET /a keys"}, three_gaps, sha256="abc")
    assert "G-02 disappeared" in problems


def test_the_gate_fails_when_a_gap_is_closed_without_proof(three_gaps):
    del three_gaps["closed"][0]["proof"]
    assert "G-03 is closed without proof" in drift(OBSERVED, three_gaps, sha256="abc")


def test_the_gate_fails_when_a_closing_test_does_not_exist(three_gaps):
    problems = drift(OBSERVED, three_gaps, sha256="abc", proof_exists=lambda proof: False)
    assert any("proof doesn't exist" in p for p in problems)


def test_the_gate_fails_when_the_contract_changes(three_gaps):
    assert any("the contract changed" in p for p in drift(OBSERVED, three_gaps, sha256="different"))


def test_the_gate_keeps_contract_and_implementation_gaps_apart(three_gaps):
    three_gaps["contract_gaps"][0]["findings"].append("missing_route GET /c")
    problems = drift(OBSERVED | {"missing_route GET /c"}, three_gaps, sha256="abc")
    assert any("contract gap but holds" in p for p in problems)
