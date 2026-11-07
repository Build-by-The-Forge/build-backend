"""Operator classification (M3-D PR 5): the tenant's authority and the
operator are checked on every run, a dry run changes nothing, each decision
is recorded whole with its audit row, rights review and outbox assignment,
repeating it changes nothing, and anything doubtful stays unclassified."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.application.content.classification import ClassificationRefused, ClassificationService, Decision
from app.application.content.read_policy import Reader
from app.db.session import SessionLocal
from app.infrastructure.content.classification_store import classification_store
from app.infrastructure.content.read_policy_sql import content_read_port
from app.infrastructure.content.scope_assignments import SqlAlchemyScopeAssignmentRepository
from app.infrastructure.db.models.content import (
    ContentAssetModel,
    ContentAuthorityAuthorizationModel,
    ContentClassificationRunModel,
    ContentOwnershipClassificationModel,
    ContentRightsAssertionModel,
    ContentScopeAssignmentModel,
    ContentSourceModel,
)
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from app.infrastructure.identity.models import UserModel

NOW = datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid4())


async def world(*, operator_role: str = "admin", documents: int = 3) -> dict:
    tag = uuid4().hex[:8]
    w = {k: _id() for k in ("tenant", "operator", "student", "source", "private_source", "authorization")}
    w["assets"] = [_id() for _ in range(documents)]
    w["personal"] = _id()
    w["in_private_source"] = _id()
    stamps = {"created_at": NOW, "updated_at": NOW}
    rows: list[object] = [
        TenantModel(id=w["tenant"], name="Classify", slug=f"cls-{tag}", status="active", **stamps),
        UserModel(id=w["operator"], email=f"op-{tag}@example.com", password_hash="x"),
        UserModel(id=w["student"], email=f"st-{tag}@example.com", password_hash="x"),
        MembershipModel(id=_id(), tenant_id=w["tenant"], user_id=w["operator"], role=operator_role, status="active", **stamps),
        MembershipModel(id=_id(), tenant_id=w["tenant"], user_id=w["student"], role="student", status="active", **stamps),
        ContentSourceModel(
            id=w["source"],
            tenant_id=w["tenant"],
            code=f"S{tag}",
            name="Staff notes",
            source_type="lecture_notes",
            authority_level="institutional",
            visibility="tenant",
            created_by=w["operator"],
            created_by_email="op@example.com",
        ),
        ContentSourceModel(
            id=w["private_source"],
            tenant_id=w["tenant"],
            code=f"P{tag}",
            name="My documents",
            source_type="lecture_notes",
            authority_level="institutional",
            visibility="private",
            owner_user_id=w["student"],
            created_by=w["student"],
            created_by_email="st@example.com",
        ),
        ContentAuthorityAuthorizationModel(
            id=w["authorization"],
            tenant_id=w["tenant"],
            authority_name="Dr A. Example",
            authority_role="Registrar",
            granted_at=NOW - timedelta(days=1),
            covers="Existing lecture notes",
            document_reference="REG/2026/014",
            recorded_by=w["operator"],
        ),
    ]

    def asset(asset_id: str, source: str, **extra) -> ContentAssetModel:
        return ContentAssetModel(
            id=asset_id,
            source_id=source,
            tenant_id=w["tenant"],
            file_name="notes.pdf",
            mime_type="application/pdf",
            file_size_bytes=1,
            content_sha256=uuid4().hex + uuid4().hex,
            storage_uri="k",
            created_by=w["operator"],
            created_by_email="op@example.com",
            **extra,
        )

    rows += [asset(a, w["source"]) for a in w["assets"]]
    rows.append(asset(w["personal"], w["source"], ownership_class="personal", owner_user_id=w["student"]))
    rows.append(asset(w["in_private_source"], w["private_source"]))
    async with SessionLocal() as session:
        for row in rows:
            session.add(row)
            await session.flush()
        await session.commit()
    return w


def decision(asset_id: str, *, ai_use: str = "permitted", evidence: str = "REG/2026/014 item 3") -> Decision:
    return Decision(asset_id, evidence, "lecturer_provided", "tenant", "tenant_only", ai_use)


def service(max_per_run: int = 50) -> ClassificationService:
    return ClassificationService(classification_store, max_per_run)


async def count(model, **where) -> int:
    async with SessionLocal() as session:
        statement = select(func.count()).select_from(model)
        for name, value in where.items():
            statement = statement.where(getattr(model, name) == value)
        return int(await session.scalar(statement))


async def classify(w, decisions, *, apply=True, operator=None, authorization=None):
    return await service().run(
        tenant_id=w["tenant"],
        operator_user_id=operator or w["operator"],
        authorization_id=authorization or w["authorization"],
        decisions=decisions,
        apply=apply,
    )


@pytest.mark.asyncio
async def test_a_dry_run_judges_every_decision_and_changes_nothing():
    w = await world()
    report = await classify(w, [decision(a) for a in w["assets"]], apply=False)
    assert [o.result for o in report.outcomes] == ["would_classify"] * 3
    assert report.run_id is None
    assert await count(ContentClassificationRunModel, tenant_id=w["tenant"]) == 0
    assert await count(ContentAssetModel, tenant_id=w["tenant"], ownership_class="institutional") == 0
    assert await count(ContentScopeAssignmentModel, tenant_id=w["tenant"]) == 0


@pytest.mark.asyncio
async def test_applying_records_each_decision_whole():
    w = await world()
    first, second, _ = w["assets"]
    report = await classify(w, [decision(first), decision(second, ai_use="not_permitted")])
    assert [(o.result, o.scope_queued) for o in report.outcomes] == [("classified", True), ("classified", False)]
    async with SessionLocal() as session:
        classes = dict(
            (
                await session.execute(
                    select(ContentAssetModel.id, ContentAssetModel.ownership_class).where(
                        ContentAssetModel.id.in_([first, second])
                    )
                )
            ).all()
        )
        audit = (
            await session.execute(
                select(ContentOwnershipClassificationModel).where(ContentOwnershipClassificationModel.asset_id == first)
            )
        ).scalar_one()
        review = (
            await session.execute(select(ContentRightsAssertionModel).where(ContentRightsAssertionModel.asset_id == first))
        ).scalar_one()
        assignments = (
            (
                await session.execute(
                    select(ContentScopeAssignmentModel).where(ContentScopeAssignmentModel.tenant_id == w["tenant"])
                )
            )
            .scalars()
            .all()
        )
    assert classes == {first: "institutional", second: "institutional"}
    # The audit row: operator, previous and new class, evidence, run.
    assert (audit.decided_by, audit.previous_class, audit.new_class, audit.decided_via, audit.run_id) == (
        w["operator"],
        "unclassified",
        "institutional",
        "operator_command",
        report.run_id,
    )
    assert audit.evidence_reference == "REG/2026/014 item 3"
    assert (review.kind, review.outcome, review.audience, review.ai_use) == ("staff_review", "accepted", "tenant", "permitted")
    # Only the document whose review permits AI use is queued, institutional at version 1.
    assert [(a.asset_id, a.scope, a.version, a.state, a.lowers) for a in assignments] == [
        (first, "institutional", 1, "pending", False)
    ]


@pytest.mark.asyncio
async def test_repeating_a_decision_changes_nothing():
    w = await world()
    await classify(w, [decision(w["assets"][0])])
    again = await classify(w, [decision(w["assets"][0])])
    assert [(o.result, o.reason) for o in again.outcomes] == [("unchanged", "ALREADY_INSTITUTIONAL")]
    assert await count(ContentOwnershipClassificationModel, asset_id=w["assets"][0]) == 1
    assert await count(ContentScopeAssignmentModel, asset_id=w["assets"][0]) == 1


@pytest.mark.asyncio
async def test_a_students_material_and_anything_doubtful_stays_unclassified():
    w = await world()
    async with SessionLocal() as session:
        await session.execute(update(ContentAssetModel).where(ContentAssetModel.id == w["assets"][1]).values(status="revoked"))
        await session.commit()
    report = await classify(
        w,
        [
            decision(w["personal"]),
            decision(w["in_private_source"]),
            decision(w["assets"][1]),
            decision(w["assets"][2], evidence="  "),
            Decision(w["assets"][0], "ref", "unknown", "tenant", "tenant_only", "permitted"),
            decision(str(uuid4())),
        ],
    )
    assert [o.reason for o in report.outcomes] == [
        "PERSONAL_DOCUMENT",
        "PERSONAL_SOURCE",
        "NOT_ACTIVE",
        "MISSING_EVIDENCE",
        "INVALID_RIGHTS_BASIS",
        "NOT_FOUND",
    ]
    assert {o.result for o in report.outcomes} == {"refused"}
    assert await count(ContentAssetModel, tenant_id=w["tenant"], ownership_class="institutional") == 0
    assert await count(ContentScopeAssignmentModel, tenant_id=w["tenant"]) == 0


@pytest.mark.asyncio
async def test_a_duplicate_in_one_run_is_refused_and_the_first_is_kept():
    w = await world()
    report = await classify(w, [decision(w["assets"][0]), decision(w["assets"][0])])
    assert [(o.result, o.reason) for o in report.outcomes] == [("classified", None), ("refused", "DUPLICATE_IN_RUN")]


@pytest.mark.asyncio
async def test_the_tenants_authority_is_checked_on_every_run():
    w, other = await world(), await world()
    async with SessionLocal() as session:
        expired = _id()
        session.add(
            ContentAuthorityAuthorizationModel(
                id=expired,
                tenant_id=w["tenant"],
                authority_name="Dr A. Example",
                authority_role="Registrar",
                granted_at=NOW - timedelta(days=30),
                expires_at=NOW - timedelta(days=1),
                covers="Old notes",
                document_reference="REG/2025/001",
                recorded_by=w["operator"],
            )
        )
        await session.commit()
    for authorization in (expired, other["authorization"], str(uuid4())):
        with pytest.raises(ClassificationRefused) as refused:
            await classify(w, [decision(w["assets"][0])], authorization=authorization)
        assert refused.value.code == "NO_TENANT_AUTHORITY"
    async with SessionLocal() as session:
        await session.execute(
            update(ContentAuthorityAuthorizationModel)
            .where(ContentAuthorityAuthorizationModel.id == w["authorization"])
            .values(revoked_at=NOW, revoked_by=w["operator"])
        )
        await session.commit()
    with pytest.raises(ClassificationRefused) as refused:
        await classify(w, [decision(w["assets"][0])])
    assert refused.value.code == "NO_TENANT_AUTHORITY"
    assert await count(ContentAssetModel, tenant_id=w["tenant"], ownership_class="institutional") == 0


@pytest.mark.asyncio
async def test_the_operator_must_manage_content_in_the_tenant():
    w = await world()
    for operator in (w["student"], str(uuid4())):
        with pytest.raises(ClassificationRefused) as refused:
            await classify(w, [decision(w["assets"][0])], operator=operator)
        assert refused.value.code == "OPERATOR_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_runs_are_bounded_and_never_empty():
    w = await world()
    with pytest.raises(ClassificationRefused) as refused:
        await ClassificationService(classification_store, 2).run(
            tenant_id=w["tenant"],
            operator_user_id=w["operator"],
            authorization_id=w["authorization"],
            decisions=[decision(a) for a in w["assets"]],
            apply=True,
        )
    assert refused.value.code == "BATCH_TOO_LARGE"
    with pytest.raises(ClassificationRefused) as refused:
        await classify(w, [])
    assert refused.value.code == "EMPTY_RUN"


@pytest.mark.asyncio
async def test_a_classified_document_reviewed_for_the_tenant_reaches_students():
    w = await world()
    student = Reader(w["tenant"], w["student"], manages_shared=False)
    async with content_read_port() as port:
        assert await port.readable_asset_ids(student, {w["assets"][0]}) == set()
    await classify(w, [decision(w["assets"][0])])
    async with content_read_port() as port:
        assert await port.readable_asset_ids(student, {w["assets"][0]}) == {w["assets"][0]}
    # Queued, not yet delivered: classification alone retrieves nothing.
    async with SessionLocal() as session:
        assert await SqlAlchemyScopeAssignmentRepository(session).pending_lowerings(w["tenant"]) == frozenset()
        state = await session.scalar(
            select(ContentScopeAssignmentModel.state).where(ContentScopeAssignmentModel.asset_id == w["assets"][0])
        )
    assert state == "pending"


@pytest.mark.asyncio
async def test_a_revocation_during_a_run_stops_every_later_decision(monkeypatch):
    # Each applied decision rechecks the authority in its own transaction; once
    # it's revoked, nothing after that point is decided on it.
    w = await world()
    real_one = ClassificationService._one
    calls = {"n": 0}

    async def one_then_revoke(self, *args, **kwargs):
        outcome = await real_one(self, *args, **kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            async with SessionLocal() as session:
                await session.execute(
                    update(ContentAuthorityAuthorizationModel)
                    .where(ContentAuthorityAuthorizationModel.id == w["authorization"])
                    .values(revoked_at=NOW, revoked_by=w["operator"])
                )
                await session.commit()
        return outcome

    monkeypatch.setattr(ClassificationService, "_one", one_then_revoke)
    report = await classify(w, [decision(a) for a in w["assets"]])
    assert [(o.result, o.reason) for o in report.outcomes] == [
        ("classified", None),
        ("refused", "NO_TENANT_AUTHORITY"),
        ("refused", "NO_TENANT_AUTHORITY"),
    ]
    assert await count(ContentAssetModel, tenant_id=w["tenant"], ownership_class="institutional") == 1


@pytest.mark.asyncio
async def test_losing_the_content_role_during_a_run_stops_every_later_decision(monkeypatch):
    w = await world()
    real_one = ClassificationService._one
    calls = {"n": 0}

    async def one_then_demote(self, *args, **kwargs):
        outcome = await real_one(self, *args, **kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            async with SessionLocal() as session:
                await session.execute(
                    update(MembershipModel)
                    .where(MembershipModel.tenant_id == w["tenant"], MembershipModel.user_id == w["operator"])
                    .values(role="student")
                )
                await session.commit()
        return outcome

    monkeypatch.setattr(ClassificationService, "_one", one_then_demote)
    report = await classify(w, [decision(a) for a in w["assets"]])
    assert [o.reason for o in report.outcomes] == [None, "OPERATOR_NOT_AUTHORIZED", "OPERATOR_NOT_AUTHORIZED"]
