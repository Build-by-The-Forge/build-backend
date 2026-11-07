"""The scope-assignment outbox on real PostgreSQL (M3-D PR 5): racing
classifications, the dispatcher's delivery rules, and immediate denial on
revocation."""

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

import app.worker as worker
from app.api.ai import pending_lowerings
from app.application.content.asset_commands import RevokeContentAssetCommand
from app.application.content.asset_handlers import RevokeContentAssetHandler
from app.db.session import SessionLocal
from app.infrastructure.content.scope_assignments import SqlAlchemyScopeAssignmentRepository
from app.infrastructure.content.scope_gateway import HttpScopeAssignmentGateway
from app.infrastructure.content.unit_of_work import ContentUnitOfWork
from app.infrastructure.db.models.content import ContentScopeAssignmentModel
from app.infrastructure.security.service_signature import ServiceKeys
from tests.integration.content.test_classification import classify, decision, world

pytestmark = pytest.mark.asyncio(loop_scope="session")


def ai_service(answer):
    """A stand-in AI service: ``answer(body) -> httpx.Response``. Records what it was sent."""
    sent: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        return answer(body)

    gateway = HttpScopeAssignmentGateway(
        base_url="http://ai-service.internal",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        keys=ServiceKeys(current="test-backend-to-ai-secret-for-scope-tests-0001"),
    )
    return gateway, sent


def holds(version_offset: int = 0):
    return lambda body: httpx.Response(
        200, json={"asset_id": body["asset_id"], "scope": body["scope"], "version": body["version"] + version_offset}
    )


async def rows(tenant_id: str) -> list[tuple[str, int, str, int]]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                ContentScopeAssignmentModel.scope,
                ContentScopeAssignmentModel.version,
                ContentScopeAssignmentModel.state,
                ContentScopeAssignmentModel.attempts,
            )
            .where(ContentScopeAssignmentModel.tenant_id == tenant_id)
            .order_by(ContentScopeAssignmentModel.version)
        )
        return [tuple(row) for row in result.all()]


async def only_this_tenant(monkeypatch, tenant_id: str) -> None:
    # Other tests leave pending rows; deliver only this world's.
    original = SqlAlchemyScopeAssignmentRepository.claim_due

    async def claim_due(self, excluded_ids):
        async with SessionLocal() as session:
            others = set(
                (
                    await session.execute(
                        select(ContentScopeAssignmentModel.id).where(
                            ContentScopeAssignmentModel.tenant_id != tenant_id,
                            ContentScopeAssignmentModel.state == "pending",
                        )
                    )
                ).scalars()
            )
        return await original(self, set(excluded_ids) | others)

    monkeypatch.setattr(SqlAlchemyScopeAssignmentRepository, "claim_due", claim_due)


async def test_two_operators_racing_on_one_document_record_it_once():
    w = await world()
    outcomes = await asyncio.gather(*(classify(w, [decision(w["assets"][0])]) for _ in range(2)))
    results = sorted(report.outcomes[0].result for report in outcomes)
    assert results == ["classified", "unchanged"]
    assert await rows(w["tenant"]) == [("institutional", 1, "pending", 0)]


async def test_a_delivered_assignment_is_acknowledged_and_a_higher_answer_supersedes(monkeypatch):
    w = await world()
    await only_this_tenant(monkeypatch, w["tenant"])
    await classify(w, [decision(w["assets"][0]), decision(w["assets"][1])])
    gateway, sent = ai_service(holds())
    monkeypatch.setattr(worker, "_scope_gateway", lambda: gateway)
    await worker.run_scope_assignment_pass()
    assert sorted((b["scope"], b["version"]) for b in sent) == [("institutional", 1), ("institutional", 1)]
    assert [state for _, _, state, _ in await rows(w["tenant"])] == ["acknowledged", "acknowledged"]


async def test_an_answer_holding_a_later_version_supersedes_ours(monkeypatch):
    # The AI service already holds a later version: ours is settled as superseded.
    w2 = await world()
    await only_this_tenant(monkeypatch, w2["tenant"])
    await classify(w2, [decision(w2["assets"][0])])
    gateway, _ = ai_service(holds(version_offset=2))
    monkeypatch.setattr(worker, "_scope_gateway", lambda: gateway)
    await worker.run_scope_assignment_pass()
    assert [state for _, _, state, _ in await rows(w2["tenant"])] == ["superseded"]


@pytest.mark.parametrize(
    "answer",
    [
        lambda body: httpx.Response(503, json={"detail": "down"}),
        lambda body: httpx.Response(409, json={"detail": "asset belongs to another tenant"}),
        lambda body: httpx.Response(200, json={"asset_id": body["asset_id"], "scope": "unknown", "version": 0}),
        lambda body: httpx.Response(200, json={"asset_id": "another", "scope": "institutional", "version": 9}),
        lambda body: httpx.Response(200, text="not json"),
    ],
    ids=["unavailable", "other-tenant", "stale", "other-asset", "unreadable"],
)
async def test_anything_but_an_answer_for_this_version_leaves_it_pending_with_backoff(monkeypatch, answer):
    w = await world()
    await only_this_tenant(monkeypatch, w["tenant"])
    await classify(w, [decision(w["assets"][0])])
    gateway, sent = ai_service(answer)
    monkeypatch.setattr(worker, "_scope_gateway", lambda: gateway)
    await worker.run_scope_assignment_pass()
    await worker.run_scope_assignment_pass()  # not due again yet: not re-sent
    assert len(sent) == 1
    assert await rows(w["tenant"]) == [("institutional", 1, "pending", 1)]


async def test_revoking_an_institutional_document_denies_it_at_once_until_acknowledged(monkeypatch):
    w = await world()
    await only_this_tenant(monkeypatch, w["tenant"])
    await classify(w, [decision(w["assets"][0]), decision(w["assets"][1])])
    gateway, _ = ai_service(holds())
    monkeypatch.setattr(worker, "_scope_gateway", lambda: gateway)
    await worker.run_scope_assignment_pass()
    assert await pending_lowerings(w["tenant"]) == frozenset()

    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await RevokeContentAssetHandler(uow).handle(
                RevokeContentAssetCommand(
                    asset_id=w["assets"][0], reason="withdrawn", revoked_by=w["operator"], tenant_id=w["tenant"]
                )
            )
    # From the revocation's commit, every retrieving call carries it.
    assert await pending_lowerings(w["tenant"]) == frozenset({w["assets"][0]})

    # The lowering goes first, then the AI service acknowledges it and it leaves the list.
    await classify(w, [decision(w["assets"][2])])
    gateway, sent = ai_service(holds())
    monkeypatch.setattr(worker, "_scope_gateway", lambda: gateway)
    await worker.run_scope_assignment_pass()
    assert sent[0] == {"asset_id": w["assets"][0], "scope": "unknown", "version": 2}
    assert await pending_lowerings(w["tenant"]) == frozenset()


async def test_revoking_a_document_never_made_institutional_queues_nothing():
    w = await world()
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await RevokeContentAssetHandler(uow).handle(
                RevokeContentAssetCommand(
                    asset_id=w["assets"][0], reason="withdrawn", revoked_by=w["operator"], tenant_id=w["tenant"]
                )
            )
    assert await rows(w["tenant"]) == []
