"""Operator classification while staff workflows are paused (M3-D PR 5).

An administrative substitute for the paused staff interface, never a weaker
standard (docs/m3-d-design.md, "Operator classification"):

1. The tenant's written authority is checked on every run.
2. Each document carries its own evidence and decision; nothing is
   classified in bulk because of where it came from.
3. Only ``unclassified`` documents, in a staff source and without an owner,
   become ``institutional``. A student's material never does.
4. The operator must hold content management in the tenant, the same check
   a staff route will make. The future staff route calls this service.
5. Per document, one transaction records the classification (the audit
   row: operator, tenant, asset, previous and new class, evidence, time,
   run), the class itself, the staff rights review, and, when AI use is
   permitted, the versioned scope assignment in the outbox.
6. A dry run is the default and writes nothing; the tenant is explicit;
   batches are bounded; repeating a decision changes nothing; every run
   produces a report, and anything refused stays unclassified.
7. Classification only queues an assignment. A document becomes
   retrievable only when the AI service acknowledges it (the dispatcher).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol

RIGHTS_BASES = frozenset({"own_work", "lecturer_provided", "institution_licensed", "publisher_licensed", "public_domain"})
AUDIENCES = frozenset({"tenant", "faculty", "department", "programme", "course"})
REDISTRIBUTION = frozenset({"none", "tenant_only", "permitted"})
AI_USE = frozenset({"not_permitted", "permitted"})


class ClassificationRefused(Exception):
    """The whole run is refused before anything is written."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Decision:
    """One document's decision and the evidence it rests on."""

    asset_id: str
    evidence_reference: str
    rights_basis: str
    audience: str
    redistribution: str
    ai_use: str


@dataclass(frozen=True, slots=True)
class DocumentState:
    tenant_id: str
    ownership_class: str
    owner_user_id: str | None
    status: str
    source_owner_user_id: str | None


@dataclass(frozen=True, slots=True)
class Outcome:
    asset_id: str
    result: str  # classified, would_classify, unchanged, refused
    reason: str | None = None
    scope_queued: bool = False


@dataclass
class RunReport:
    tenant_id: str
    authorization_id: str
    operator_user_id: str
    applied: bool
    run_id: str | None = None
    outcomes: list[Outcome] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self.outcomes:
            counts[outcome.result] = counts.get(outcome.result, 0) + 1
        return counts


def invalid_decision(decision: Decision) -> str | None:
    """Why a decision can't be recorded as written, or None."""
    if not decision.asset_id.strip():
        return "MISSING_ASSET"
    if not decision.evidence_reference.strip():
        return "MISSING_EVIDENCE"
    if decision.rights_basis not in RIGHTS_BASES:
        return "INVALID_RIGHTS_BASIS"
    if decision.audience not in AUDIENCES:
        return "INVALID_AUDIENCE"
    if decision.redistribution not in REDISTRIBUTION:
        return "INVALID_REDISTRIBUTION"
    if decision.ai_use not in AI_USE:
        return "INVALID_AI_USE"
    return None


def judge(document: DocumentState | None, decision: Decision) -> tuple[str, str | None]:
    """The rule for one document: ("classify", None), ("unchanged", reason)
    or ("refuse", reason). Ambiguity refuses, and the document stays put."""
    invalid = invalid_decision(decision)
    if invalid is not None:
        return "refuse", invalid
    if document is None:
        return "refuse", "NOT_FOUND"
    if document.ownership_class == "personal" or document.owner_user_id is not None:
        return "refuse", "PERSONAL_DOCUMENT"
    if document.source_owner_user_id is not None:
        return "refuse", "PERSONAL_SOURCE"
    if document.status != "active":
        return "refuse", "NOT_ACTIVE"
    if document.ownership_class == "institutional":
        return "unchanged", "ALREADY_INSTITUTIONAL"
    if document.ownership_class != "unclassified":
        return "refuse", "NOT_UNCLASSIFIED"
    return "classify", None


class ClassificationStore(Protocol):
    """One transaction: committed when its context exits cleanly."""

    async def authorization_valid(self, tenant_id: str, authorization_id: str) -> bool: ...

    async def operator_manages_content(self, tenant_id: str, user_id: str) -> bool: ...

    async def document(self, tenant_id: str, asset_id: str, *, lock: bool) -> DocumentState | None: ...

    async def create_run(self, tenant_id: str, authorization_id: str, operator_user_id: str, requested: int) -> str: ...

    async def record(self, tenant_id: str, decision: Decision, operator_user_id: str, run_id: str) -> bool:
        """Record the decision; True if a scope assignment was queued."""
        ...


class ClassificationService:
    def __init__(self, store_factory: Callable[[], AbstractAsyncContextManager[ClassificationStore]], max_per_run: int) -> None:
        self._store = store_factory
        self._max = max_per_run

    async def run(
        self,
        *,
        tenant_id: str,
        operator_user_id: str,
        authorization_id: str,
        decisions: Sequence[Decision],
        apply: bool = False,
    ) -> RunReport:
        if not decisions:
            raise ClassificationRefused("EMPTY_RUN", "no decisions to record")
        if len(decisions) > self._max:
            raise ClassificationRefused("BATCH_TOO_LARGE", f"at most {self._max} decisions per run")
        async with self._store() as store:
            if not await store.authorization_valid(tenant_id, authorization_id):
                raise ClassificationRefused(
                    "NO_TENANT_AUTHORITY", "no current written authorization from this tenant's authority"
                )
            if not await store.operator_manages_content(tenant_id, operator_user_id):
                raise ClassificationRefused("OPERATOR_NOT_AUTHORIZED", "the operator doesn't manage content in this tenant")

        report = RunReport(tenant_id, authorization_id, operator_user_id, applied=apply)
        if apply:
            async with self._store() as store:
                report.run_id = await store.create_run(tenant_id, authorization_id, operator_user_id, len(decisions))

        seen: set[str] = set()
        for decision in decisions:
            if decision.asset_id in seen:
                report.outcomes.append(Outcome(decision.asset_id, "refused", "DUPLICATE_IN_RUN"))
                continue
            seen.add(decision.asset_id)
            report.outcomes.append(await self._one(tenant_id, operator_user_id, report.run_id, decision, apply))
        return report

    async def _one(self, tenant_id: str, operator_user_id: str, run_id: str | None, decision: Decision, apply: bool) -> Outcome:
        # Each document in its own transaction: its decision is recorded
        # whole or not at all, whatever happens to the others.
        async with self._store() as store:
            document = await store.document(tenant_id, decision.asset_id, lock=apply)
            verdict, reason = judge(document, decision)
            if verdict == "refuse":
                return Outcome(decision.asset_id, "refused", reason)
            if verdict == "unchanged":
                return Outcome(decision.asset_id, "unchanged", reason)
            if not apply or run_id is None:
                return Outcome(decision.asset_id, "would_classify", scope_queued=decision.ai_use == "permitted")
            queued = await store.record(tenant_id, decision, operator_user_id, run_id)
            return Outcome(decision.asset_id, "classified", scope_queued=queued)
