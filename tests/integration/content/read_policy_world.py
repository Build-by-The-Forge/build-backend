"""Every row of the design's read-policy table as real rows, for checking the
SQL predicate against ``may_read`` (M3-D PR 4). Shared by the SQLite test and
the PostgreSQL one, so both databases are held to the same table."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.content.read_policy import DocumentFacts, Reader
from app.db.session import SessionLocal
from app.infrastructure.db.models.content import (
    ContentAssetModel,
    ContentPublicationModel,
    ContentRightsAssertionModel,
    ContentSourceModel,
)
from app.infrastructure.db.models.tenant_core import TenantModel
from app.infrastructure.identity.models import UserModel


def _id() -> str:
    return str(uuid4())


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
FUTURE = frozenset({"quarantined", "rejected", "deleted"})


@dataclass(frozen=True)
class Doc:
    name: str
    facts: DocumentFacts
    owner: str | None = None  # a key into World.users
    reviews: tuple[tuple[str, str], ...] = ()  # (outcome, audience), oldest first
    publication: str | None = None  # publication state
    hidden: bool = False


@dataclass
class World:
    tenant: str
    other_tenant: str
    users: dict[str, str]
    readers: dict[str, Reader]
    assets: dict[str, str]  # doc name -> asset id
    docs: dict[str, Doc]


def _facts(
    tenant: str | None, ownership: str, *, status="active", owner=None, ingestion="ready", published=False, reviewed=False
):
    return DocumentFacts(
        tenant_id=tenant,
        status=status,
        ownership_class=ownership,
        owner_user_id=owner,
        ingestion_status=ingestion,
        published=published,
        reviewed_for_students=reviewed,
    )


async def build_world(*, future_states: bool = True) -> World:
    """``future_states=False`` leaves out the rows whose status the domain
    doesn't model yet (the scan's quarantined and rejected, PR 6; deleted,
    PR 11), for tests that map rows to domain objects."""
    tag = uuid4().hex[:8]
    tenant, other_tenant = _id(), _id()
    users = {k: _id() for k in ("owner", "student", "staff", "other_staff", "other_student")}
    readers = {
        "owner": Reader(tenant, users["owner"], manages_shared=False),
        "student": Reader(tenant, users["student"], manages_shared=False),
        "staff": Reader(tenant, users["staff"], manages_shared=True),
        "other_staff": Reader(other_tenant, users["other_staff"], manages_shared=True),
        "other_student": Reader(other_tenant, users["other_student"], manages_shared=False),
    }
    owner = users["owner"]
    specs = [
        Doc("personal private", _facts(tenant, "personal", owner=owner), owner="owner"),
        Doc(
            "personal published",
            _facts(tenant, "personal", owner=owner, published=True),
            owner="owner",
            publication="published",
        ),
        Doc(
            "personal published, quarantined",
            _facts(tenant, "personal", owner=owner, ingestion="quarantined", published=True),
            owner="owner",
            publication="published",
        ),
        Doc(
            "personal published, rejected by the scan",
            _facts(tenant, "personal", owner=owner, ingestion="rejected", published=True),
            owner="owner",
            publication="published",
        ),
        Doc(
            "personal published, hidden",
            _facts(tenant, "personal", owner=owner),
            owner="owner",
            publication="published",
            hidden=True,
        ),
        Doc("personal, publication requested", _facts(tenant, "personal", owner=owner), owner="owner", publication="requested"),
        Doc("personal deleted", _facts(tenant, "personal", owner=owner, status="deleted"), owner="owner"),
        Doc("personal revoked", _facts(tenant, "personal", owner=owner, status="revoked"), owner="owner"),
        Doc("institutional, not reviewed", _facts(tenant, "institutional")),
        Doc(
            "institutional, reviewed for the tenant",
            _facts(tenant, "institutional", reviewed=True),
            reviews=(("accepted", "tenant"),),
        ),
        Doc(
            "institutional, reviewed for a course only",
            _facts(tenant, "institutional"),
            reviews=(("accepted", "course"),),
        ),
        Doc(
            "institutional, accepted then rejected",
            _facts(tenant, "institutional"),
            reviews=(("accepted", "tenant"), ("rejected", "tenant")),
        ),
        Doc(
            "institutional, rejected then accepted",
            _facts(tenant, "institutional", reviewed=True),
            reviews=(("rejected", "tenant"), ("accepted", "tenant")),
        ),
        Doc(
            "institutional, reviewed, revoked",
            _facts(tenant, "institutional", status="revoked", reviewed=True),
            reviews=(("accepted", "tenant"),),
        ),
        Doc("institutional, superseded", _facts(tenant, "institutional", status="superseded")),
        Doc("unclassified", _facts(tenant, "unclassified")),
        Doc("unclassified, revoked", _facts(tenant, "unclassified", status="revoked")),
        Doc("platform", _facts(None, "unclassified")),
        Doc(
            "another tenant's, reviewed",
            _facts(other_tenant, "institutional", reviewed=True),
            reviews=(("accepted", "tenant"),),
        ),
        Doc("another tenant's unclassified", _facts(other_tenant, "unclassified")),
    ]

    if not future_states:
        specs = [d for d in specs if d.facts.ingestion_status not in FUTURE and d.facts.status not in FUTURE]

    now = datetime.now(timezone.utc)
    stamps = {"created_at": now, "updated_at": now}
    rows: list[object] = [
        TenantModel(id=t, name="Policy", slug=f"policy-{t[:8]}", status="active", **stamps) for t in (tenant, other_tenant)
    ]
    rows += [UserModel(id=user, email=f"policy-{name}-{tag}@example.com", password_hash="x") for name, user in users.items()]
    sources = {t: _id() for t in (tenant, other_tenant, None)}
    rows += [
        ContentSourceModel(
            id=source,
            tenant_id=t,
            code=f"P{uuid4().hex[:10]}",
            name="Staff",
            source_type="lecture_notes",
            authority_level="institutional",
            visibility="tenant",
            created_by=users["staff"],
            created_by_email="staff@example.com",
        )
        for t, source in sources.items()
    ]
    assets: dict[str, str] = {}
    later: list[object] = []
    for doc in specs:
        asset = _id()
        assets[doc.name] = asset
        f = doc.facts
        rows.append(
            ContentAssetModel(
                id=asset,
                source_id=sources[f.tenant_id],
                tenant_id=f.tenant_id,
                file_name="f.pdf",
                mime_type="application/pdf",
                file_size_bytes=1,
                content_sha256=uuid4().hex + uuid4().hex,
                storage_uri="k",
                status=f.status,
                ingestion_status=f.ingestion_status,
                created_by=users["staff"],
                created_by_email="staff@example.com",
                ownership_class=f.ownership_class,
                owner_user_id=users[doc.owner] if doc.owner else None,
            )
        )
        for n, (outcome, audience) in enumerate(doc.reviews):
            later.append(
                ContentRightsAssertionModel(
                    id=_id(),
                    tenant_id=f.tenant_id,
                    asset_id=asset,
                    asserted_by=users["staff"],
                    kind="staff_review",
                    rights_basis="lecturer_provided",
                    audience=audience,
                    redistribution="tenant_only",
                    ai_use="not_permitted",
                    outcome=outcome,
                    reason="reviewed",
                    asserted_at=T0 + timedelta(minutes=n),
                )
            )
        if doc.publication:
            declaration = _id()
            later.append(
                ContentRightsAssertionModel(
                    id=declaration,
                    tenant_id=f.tenant_id,
                    asset_id=asset,
                    asserted_by=users[doc.owner],
                    kind="owner_declaration",
                    rights_basis="own_work",
                    audience="tenant",
                    redistribution="tenant_only",
                    ai_use="not_permitted",
                    declaration_version="v1",
                    asserted_at=T0,
                )
            )
            later.append(
                ContentPublicationModel(
                    id=_id(),
                    tenant_id=f.tenant_id,
                    asset_id=asset,
                    declaration_id=declaration,
                    requested_by=users[doc.owner],
                    consent_version="c1",
                    state=doc.publication,
                    requested_at=T0,
                    published_at=T0 if doc.publication == "published" else None,
                    hidden_at=T0 if doc.hidden else None,
                )
            )
    async with SessionLocal() as session:
        for row in rows + later:  # parents first, for the foreign keys
            session.add(row)
            await session.flush()
        await session.commit()
    docs = {doc.name: replace(doc) for doc in specs}
    return World(tenant, other_tenant, users, readers, assets, docs)
