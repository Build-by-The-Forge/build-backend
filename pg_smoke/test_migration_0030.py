"""Migration 0030 on real PostgreSQL: each rule in docs/m3-d-migration-0030.md's
test table, against the migrated schema.

Every check that must hold against NULL is tested with NULL, every composite
reference with another tenant's row, and every partial index past five runs
with literal predicates.
"""

import asyncio
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.session import SessionLocal
from app.infrastructure.content.job_repositories import SqlAlchemyContentIngestionJobRepository, is_active_job_conflict
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.content import ContentAssetModel, ContentSourceModel
from app.infrastructure.db.models.tenant_core import DepartmentModel, FacultyModel, TenantModel
from app.infrastructure.identity.models import UserModel
from scripts._read_only_report import _rows as _read_only_rows

pytestmark = pytest.mark.asyncio(loop_scope="session")

REFUSED = (IntegrityError, DBAPIError)
SHA = "ab" * 32


def _id() -> str:
    return str(uuid4())


async def _world() -> dict[str, str]:
    """A tenant with a faculty, department and course, a user, a staff source and
    a document, built through the models so their defaults apply."""
    now = datetime.now(timezone.utc)
    stamps = {"status": "active", "created_at": now, "updated_at": now}
    tag = uuid4().hex[:8]
    w = {k: _id() for k in ("tenant", "faculty", "department", "course", "user", "source", "asset")}
    rows = [
        TenantModel(id=w["tenant"], name="M30", slug=f"m30-{tag}", **stamps),
        FacultyModel(id=w["faculty"], tenant_id=w["tenant"], name="F", slug=f"f-{tag}", **stamps),
        DepartmentModel(
            id=w["department"],
            tenant_id=w["tenant"],
            faculty_id=w["faculty"],
            name="D",
            slug=f"d-{tag}",
            code=f"D{tag}",
            **stamps,
        ),
        CourseModel(
            id=w["course"],
            tenant_id=w["tenant"],
            department_id=w["department"],
            code=f"C{tag}",
            title="C",
            slug=f"c-{tag}",
            credit_units=3,
            level=100,
            semester=1,
            **stamps,
        ),
        UserModel(id=w["user"], email=f"m30-{tag}@example.com", password_hash="x"),
        ContentSourceModel(
            id=w["source"],
            tenant_id=w["tenant"],
            code=f"S{tag}",
            name="Staff source",
            source_type="lecture_notes",
            authority_level="institutional",
            visibility="tenant",
            created_by=w["user"],
            created_by_email="staff@example.com",
        ),
        ContentAssetModel(
            id=w["asset"],
            source_id=w["source"],
            tenant_id=w["tenant"],
            file_name="notes.pdf",
            mime_type="application/pdf",
            file_size_bytes=10,
            content_sha256=uuid4().hex + uuid4().hex,
            storage_uri=f"tenants/{w['tenant']}/assets/{w['asset']}/x",
            created_by=w["user"],
            created_by_email="staff@example.com",
        ),
    ]
    async with SessionLocal() as session:
        for row in rows:  # parents first, for the foreign keys
            session.add(row)
            await session.flush()
        await session.commit()
    return w


async def _run(sql: str, **params) -> None:
    async with SessionLocal() as session, session.begin():
        await session.execute(text(sql), params)


async def _refused(sql: str, **params) -> None:
    with pytest.raises(REFUSED):
        await _run(sql, **params)


async def _scalar(sql: str, **params):
    async with SessionLocal() as session:
        return (await session.execute(text(sql), params)).scalar()


async def _rows(sql: str, **params) -> list:
    async with SessionLocal() as session:
        return list((await session.execute(text(sql), params)).scalars())


async def _asset(
    w: dict[str, str], *, sha: str, owner: str | None = None, cls: str = "unclassified", status: str = "active"
) -> str:
    asset = _id()
    await _run(
        "INSERT INTO content_assets (id, source_id, tenant_id, file_name, mime_type, file_size_bytes, content_sha256,"
        " storage_uri, asset_version, status, ingestion_status, metadata, created_by, created_by_email,"
        " created_at, updated_at, ownership_class, owner_user_id)"
        " VALUES (:id, :s, :t, 'f', 'application/pdf', 1, :sha, 'k', 1, :st, 'uploaded', '{}', :u, 'e', now(), now(), :c, :o)",
        id=asset,
        s=w["source"],
        t=w["tenant"],
        sha=sha,
        st=status,
        u=w["user"],
        c=cls,
        o=owner,
    )
    return asset


# --- Existing rows and the round trip ---------------------------------------------------


async def test_an_existing_document_is_unclassified_with_no_owner():
    w = await _world()
    row = await _scalar(
        "SELECT ownership_class || ':' || coalesce(owner_user_id, '-') FROM content_assets WHERE id = :a", a=w["asset"]
    )
    assert row == "unclassified:-"


async def test_shared_material_stays_unique_per_tenant_as_before():
    w = await _world()
    for _ in range(7):  # past five runs
        sha = uuid4().hex + uuid4().hex
        await _asset(w, sha=sha)
        await _refused(
            "INSERT INTO content_assets (id, source_id, tenant_id, file_name, mime_type, file_size_bytes, content_sha256,"
            " storage_uri, asset_version, status, ingestion_status, metadata, created_by, created_by_email,"
            " created_at, updated_at)"
            " VALUES (:id, :s, :t, 'f', 'application/pdf', 1, :sha, 'k', 1, 'active', 'uploaded', '{}', :u, 'e', now(), now())",
            id=_id(),
            s=w["source"],
            t=w["tenant"],
            sha=sha,
            u=w["user"],
        )


# --- Required values: NULL never satisfies a check ------------------------------------


@pytest.mark.parametrize(
    "outcome,reason",
    [(None, "fine"), ("accepted", None), ("accepted", "   "), (None, None)],
    ids=["no-outcome", "no-reason", "blank-reason", "neither"],
)
async def test_a_staff_review_needs_an_outcome_and_a_reason(outcome, reason):
    w = await _world()
    await _refused(
        "INSERT INTO content_rights_assertions (id, tenant_id, asset_id, asserted_by, kind, rights_basis, audience,"
        " redistribution, outcome, reason) VALUES (:id, :t, :a, :u, 'staff_review', 'unknown', 'tenant', 'none', :o, :r)",
        id=_id(),
        t=w["tenant"],
        a=w["asset"],
        u=w["user"],
        o=outcome,
        r=reason,
    )


async def test_an_owner_declaration_needs_its_version_and_a_non_review_has_no_outcome():
    w = await _world()
    base = (
        "INSERT INTO content_rights_assertions (id, tenant_id, asset_id, asserted_by, kind, rights_basis, audience,"
        " redistribution, declaration_version, outcome) VALUES (:id, :t, :a, :u, :k, 'own_work', 'tenant', 'tenant_only', :v, :o)"
    )
    args = {"t": w["tenant"], "a": w["asset"], "u": w["user"]}
    await _refused(base, id=_id(), k="owner_declaration", v=None, o=None, **args)
    await _refused(base, id=_id(), k="owner_declaration", v=" ", o=None, **args)
    await _refused(base, id=_id(), k="owner_declaration", v="v1", o="accepted", **args)
    await _run(base, id=_id(), k="owner_declaration", v="v1", o=None, **args)


@pytest.mark.parametrize("column", ["ownership_class", "state", "verdict"])
async def test_status_columns_refuse_null(column):
    w = await _world()
    if column == "ownership_class":
        await _refused("UPDATE content_assets SET ownership_class = NULL WHERE id = :a", a=w["asset"])
    elif column == "state":
        await _refused(
            "INSERT INTO content_blobs (id, tenant_id, content_sha256, size_bytes, mime_type, generation, object_key, state)"
            " VALUES (:id, :t, :sha, 1, 'application/pdf', :g, :k, NULL)",
            id=_id(),
            t=w["tenant"],
            sha=SHA,
            g=_id(),
            k=_id(),
        )
    else:
        await _refused(
            "INSERT INTO content_scans (asset_id, tenant_id, verdict) VALUES (:a, :t, NULL)", a=w["asset"], t=w["tenant"]
        )


async def test_a_scan_verdict_needs_its_scanner_signature_and_time():
    w = await _world()
    await _run("INSERT INTO content_scans (asset_id, tenant_id) VALUES (:a, :t)", a=w["asset"], t=w["tenant"])
    await _refused("UPDATE content_scans SET verdict = 'accepted' WHERE asset_id = :a", a=w["asset"])
    await _run(
        "UPDATE content_scans SET verdict = 'accepted', scanner = 'clamd', signature_version = '27000', scanned_at = now()"
        " WHERE asset_id = :a",
        a=w["asset"],
    )


async def test_the_operator_command_needs_a_run_and_evidence():
    w = await _world()
    base = (
        "INSERT INTO content_ownership_classifications (id, tenant_id, asset_id, previous_class, new_class, decided_by,"
        " decided_via, evidence_reference, run_id) VALUES (:id, :t, :a, 'unclassified', 'institutional', :u, :via, :e, :r)"
    )
    args = {"t": w["tenant"], "a": w["asset"], "u": w["user"]}
    await _refused(base, id=_id(), via="operator_command", e="ref-1", r=None, **args)
    await _refused(base, id=_id(), via="staff_route", e="  ", r=None, **args)
    await _run(base, id=_id(), via="operator_command", e="ref-1", r=_id(), **args)


# --- Ownership -------------------------------------------------------------------------


async def test_a_personal_document_needs_an_owner_and_only_it_has_one():
    w = await _world()
    await _refused("UPDATE content_assets SET ownership_class = 'personal' WHERE id = :a", a=w["asset"])
    await _refused("UPDATE content_assets SET owner_user_id = :u WHERE id = :a", a=w["asset"], u=w["user"])
    await _run(
        "UPDATE content_assets SET ownership_class = 'personal', owner_user_id = :u WHERE id = :a", a=w["asset"], u=w["user"]
    )


async def test_a_private_source_needs_an_owner_and_there_is_one_per_student():
    w = await _world()
    insert = (
        "INSERT INTO content_sources (id, tenant_id, code, name, source_type, authority_level, visibility, status,"
        " trust_policy, created_by, created_by_email, created_at, updated_at, owner_user_id)"
        " VALUES (:id, :t, :c, 'Mine', 'personal', 'user_provided', :v, 'active', '{}', :u, 'e', now(), now(), :o)"
    )
    await _refused(insert, id=_id(), t=w["tenant"], c="P0", v="private", u=w["user"], o=None)
    await _refused(insert, id=_id(), t=w["tenant"], c="P1", v="tenant", u=w["user"], o=w["user"])

    async def create(code: str) -> bool:
        try:
            await _run(insert, id=_id(), t=w["tenant"], c=code, v="private", u=w["user"], o=w["user"])
            return True
        except REFUSED:
            return False

    assert sorted(await asyncio.gather(create("P2"), create("P3"))) == [False, True]


# --- The hash indexes and deletion -------------------------------------------------------


async def test_two_students_may_hold_the_same_bytes_and_one_can_hold_them_again_after_deleting():
    w = await _world()
    other = _id()
    await _run(
        "INSERT INTO users (id, email, password_hash, status, is_verified, is_active, created_at, updated_at, version)"
        " VALUES (:id, :e, 'x', 'ACTIVE', true, true, now(), now(), 0)",
        id=other,
        e=f"other-{other}@example.com",
    )
    for _ in range(6):  # past five runs
        sha = uuid4().hex + uuid4().hex
        first = await _asset(w, sha=sha, owner=w["user"], cls="personal")
        await _asset(w, sha=sha, owner=other, cls="personal")
        with pytest.raises(REFUSED):
            await _asset(w, sha=sha, owner=w["user"], cls="personal")
        await _run("UPDATE content_assets SET status = 'deleted' WHERE id = :a", a=first)
        await _asset(w, sha=sha, owner=w["user"], cls="personal")


async def test_shared_bytes_upload_again_after_deletion_but_revoked_still_blocks():
    w = await _world()
    sha = uuid4().hex + uuid4().hex
    first = await _asset(w, sha=sha)
    await _run("UPDATE content_assets SET status = 'revoked' WHERE id = :a", a=first)
    with pytest.raises(REFUSED):
        await _asset(w, sha=sha)
    await _run("UPDATE content_assets SET status = 'deleted' WHERE id = :a", a=first)
    await _asset(w, sha=sha)


# --- Tenant consistency ------------------------------------------------------------------


async def test_a_row_cant_point_at_another_tenants_asset_course_or_blob():
    w, other = await _world(), await _world()
    await _refused("INSERT INTO content_scans (asset_id, tenant_id) VALUES (:a, :t)", a=other["asset"], t=w["tenant"])
    await _refused(
        "INSERT INTO content_retry_usage (tenant_id, asset_id, usage_day) VALUES (:t, :a, :d)",
        t=w["tenant"],
        a=other["asset"],
        d=date.today(),
    )
    await _refused("UPDATE content_assets SET course_id = :c WHERE id = :a", c=other["course"], a=w["asset"])
    blob = _id()
    await _run(
        "INSERT INTO content_blobs (id, tenant_id, content_sha256, size_bytes, mime_type, generation, object_key, state,"
        " claimed_until) VALUES (:id, :t, :sha, 1, 'application/pdf', :g, :k, 'pending', now())",
        id=blob,
        t=other["tenant"],
        sha=SHA,
        g=_id(),
        k=_id(),
    )
    await _refused("UPDATE content_assets SET blob_id = :b WHERE id = :a", b=blob, a=w["asset"])
    await _run("UPDATE content_assets SET course_id = :c WHERE id = :a", c=w["course"], a=w["asset"])


async def test_a_tenantless_document_cant_carry_a_course_or_a_blob():
    w = await _world()
    await _refused("UPDATE content_assets SET tenant_id = NULL, course_id = :c WHERE id = :a", c=w["course"], a=w["asset"])
    await _refused("UPDATE content_assets SET tenant_id = NULL, blob_id = :b WHERE id = :a", b=_id(), a=w["asset"])


async def test_a_publication_names_a_declaration_of_its_own_document():
    w = await _world()
    second = await _asset(w, sha=uuid4().hex + uuid4().hex)
    declaration = _id()
    await _run(
        "INSERT INTO content_rights_assertions (id, tenant_id, asset_id, asserted_by, kind, rights_basis, audience,"
        " redistribution, declaration_version) VALUES (:id, :t, :a, :u, 'owner_declaration', 'own_work', 'tenant',"
        " 'tenant_only', 'v1')",
        id=declaration,
        t=w["tenant"],
        a=w["asset"],
        u=w["user"],
    )
    insert = (
        "INSERT INTO content_publications (id, tenant_id, asset_id, declaration_id, requested_by, consent_version)"
        " VALUES (:id, :t, :a, :d, :u, 'c1')"
    )
    await _refused(insert, id=_id(), t=w["tenant"], a=second, d=declaration, u=w["user"])
    await _run(insert, id=_id(), t=w["tenant"], a=w["asset"], d=declaration, u=w["user"])


# --- Blobs -------------------------------------------------------------------------------


async def test_one_live_blob_per_bytes_and_the_claim_rules():
    w = await _world()
    insert = (
        "INSERT INTO content_blobs (id, tenant_id, content_sha256, size_bytes, mime_type, generation, object_key, state,"
        " claimed_until) VALUES (:id, :t, :sha, 1, 'application/pdf', :g, :k, :s, :c)"
    )
    sha = uuid4().hex + uuid4().hex
    now = datetime.now(timezone.utc)
    await _refused(insert, id=_id(), t=w["tenant"], sha=sha, g=_id(), k=_id(), s="pending", c=None)
    await _refused(insert, id=_id(), t=w["tenant"], sha=sha, g=_id(), k=_id(), s="active", c=now)
    live = _id()
    await _run(insert, id=live, t=w["tenant"], sha=sha, g=_id(), k=_id(), s="pending", c=now + timedelta(minutes=5))
    await _refused(insert, id=_id(), t=w["tenant"], sha=sha, g=_id(), k=_id(), s="pending", c=now)
    await _refused("UPDATE content_blobs SET state = 'active' WHERE id = :b", b=live)
    await _run("UPDATE content_blobs SET state = 'deleting' WHERE id = :b", b=live)
    await _run(insert, id=_id(), t=w["tenant"], sha=sha, g=_id(), k=_id(), s="active", c=None)


# --- Append-only, cascades and audit retention -------------------------------------------


async def test_classifications_and_rights_are_append_only_but_a_tenant_cascade_removes_them():
    w = await _world()
    classification, assertion = _id(), _id()
    await _run(
        "INSERT INTO content_ownership_classifications (id, tenant_id, asset_id, previous_class, new_class, decided_by,"
        " decided_via, evidence_reference) VALUES (:id, :t, :a, 'unclassified', 'institutional', :u, 'staff_route', 'ref')",
        id=classification,
        t=w["tenant"],
        a=w["asset"],
        u=w["user"],
    )
    await _run(
        "INSERT INTO content_rights_assertions (id, tenant_id, asset_id, asserted_by, kind, rights_basis, audience,"
        " redistribution, declaration_version) VALUES (:id, :t, :a, :u, 'owner_declaration', 'own_work', 'tenant',"
        " 'tenant_only', 'v1')",
        id=assertion,
        t=w["tenant"],
        a=w["asset"],
        u=w["user"],
    )
    await _refused("UPDATE content_ownership_classifications SET evidence_reference = 'x' WHERE id = :i", i=classification)
    await _refused("DELETE FROM content_ownership_classifications WHERE id = :i", i=classification)
    await _refused("UPDATE content_rights_assertions SET rights_basis = 'unknown' WHERE id = :i", i=assertion)
    await _refused("DELETE FROM content_rights_assertions WHERE id = :i", i=assertion)
    # Deleting a user referenced by an audit record is refused.
    await _refused("DELETE FROM users WHERE id = :u", u=w["user"])
    await _run("DELETE FROM tenants WHERE id = :t", t=w["tenant"])
    assert await _scalar("SELECT count(*) FROM content_ownership_classifications WHERE id = :i", i=classification) == 0
    assert await _scalar("SELECT count(*) FROM content_rights_assertions WHERE id = :i", i=assertion) == 0


# --- Publication ---------------------------------------------------------------------------


async def _declared(w: dict[str, str]) -> str:
    declaration = _id()
    await _run(
        "INSERT INTO content_rights_assertions (id, tenant_id, asset_id, asserted_by, kind, rights_basis, audience,"
        " redistribution, declaration_version) VALUES (:id, :t, :a, :u, 'owner_declaration', 'own_work', 'tenant',"
        " 'tenant_only', 'v1')",
        id=declaration,
        t=w["tenant"],
        a=w["asset"],
        u=w["user"],
    )
    return declaration


async def test_one_live_publication_per_document_under_a_race():
    w = await _world()
    declaration = await _declared(w)

    async def request() -> bool:
        try:
            await _run(
                "INSERT INTO content_publications (id, tenant_id, asset_id, declaration_id, requested_by, consent_version)"
                " VALUES (:id, :t, :a, :d, :u, 'c1')",
                id=_id(),
                t=w["tenant"],
                a=w["asset"],
                d=declaration,
                u=w["user"],
            )
            return True
        except REFUSED:
            return False

    assert sorted(await asyncio.gather(*(request() for _ in range(4)))) == [False, False, False, True]


async def test_publication_transitions_and_consent_are_enforced():
    w = await _world()
    declaration = await _declared(w)
    publication = _id()
    await _run(
        "INSERT INTO content_publications (id, tenant_id, asset_id, declaration_id, requested_by, consent_version)"
        " VALUES (:id, :t, :a, :d, :u, 'c1')",
        id=publication,
        t=w["tenant"],
        a=w["asset"],
        d=declaration,
        u=w["user"],
    )
    await _refused("UPDATE content_publications SET consent_version = 'c2' WHERE id = :p", p=publication)
    await _refused(
        "UPDATE content_publications SET state = 'taken_down', ended_at = now(), ended_by = :u, end_reason = 'x',"
        " published_at = now() WHERE id = :p",
        p=publication,
        u=w["user"],
    )
    await _run("UPDATE content_publications SET state = 'published', published_at = now() WHERE id = :p", p=publication)
    await _refused(
        "UPDATE content_publications SET state = 'taken_down', ended_at = now(), ended_by = :u WHERE id = :p",
        p=publication,
        u=w["user"],
    )
    await _run(
        "UPDATE content_publications SET state = 'taken_down', ended_at = now(), ended_by = :u, end_reason = 'exam'"
        " WHERE id = :p",
        p=publication,
        u=w["user"],
    )
    await _refused("UPDATE content_publications SET state = 'published', ended_at = NULL WHERE id = :p", p=publication)
    await _refused("DELETE FROM content_publications WHERE id = :p", p=publication)


# --- Quotas ---------------------------------------------------------------------------------


async def test_uploads_racing_at_the_limit_charge_exactly_the_allowed_number():
    w = await _world()
    await _run(
        "INSERT INTO content_upload_usage (tenant_id, owner_user_id, usage_day, uploads_on_day) VALUES (:t, :u, :d, 47)",
        t=w["tenant"],
        u=w["user"],
        d=date.today(),
    )

    async def charge() -> bool:
        async with SessionLocal() as session, session.begin():
            result = await session.execute(
                text(
                    "UPDATE content_upload_usage SET uploads_on_day = uploads_on_day + 1"
                    " WHERE tenant_id = :t AND owner_user_id = :u AND uploads_on_day < 50"
                ),
                {"t": w["tenant"], "u": w["user"]},
            )
            return result.rowcount == 1

    results = await asyncio.gather(*(charge() for _ in range(8)))
    assert sum(results) == 3
    assert (
        await _scalar(
            "SELECT uploads_on_day FROM content_upload_usage WHERE tenant_id = :t AND owner_user_id = :u",
            t=w["tenant"],
            u=w["user"],
        )
        == 50
    )


async def test_usage_never_goes_negative():
    w = await _world()
    await _refused(
        "INSERT INTO content_upload_usage (tenant_id, owner_user_id, usage_day, stored_bytes) VALUES (:t, :u, :d, -1)",
        t=w["tenant"],
        u=w["user"],
        d=date.today(),
    )


# --- Active jobs ------------------------------------------------------------------------------


async def test_a_second_active_job_on_one_asset_is_refused():
    w = await _world()
    insert = (
        "INSERT INTO content_ingestion_jobs (id, asset_id, source_id, tenant_id, run_number, status, attempt_count,"
        " max_attempts, error_details, is_retryable, metrics, attempt_history, created_by, created_at, updated_at)"
        " VALUES (:id, :a, :s, :t, :r, :st, 1, 3, '{}', false, '{}', '[]', :u, now(), now())"
    )
    args = {"a": w["asset"], "s": w["source"], "t": w["tenant"], "u": w["user"]}
    for _ in range(6):  # past five runs
        await _run(insert, id=_id(), r=1, st="ready", **args)
    await _run(insert, id=_id(), r=2, st="queued", **args)
    with pytest.raises(IntegrityError) as refused:
        await _run(insert, id=_id(), r=3, st="processing", **args)
    # The job routes recognise exactly this refusal and answer ACTIVE_JOB_EXISTS.
    assert is_active_job_conflict(refused.value)


async def test_the_retrier_skips_a_failure_whose_document_has_an_active_run():
    insert = (
        "INSERT INTO content_ingestion_jobs (id, asset_id, source_id, tenant_id, run_number, status, attempt_count,"
        " max_attempts, error_details, is_retryable, metrics, attempt_history, created_by, created_at, updated_at)"
        " VALUES (:id, :a, :s, :t, :r, :st, 1, 3, '{}', true, '{}', '[]', :u, now() - interval '1 day',"
        " now() - interval '1 day')"
    )
    blocked, free = await _world(), await _world()
    failures = {}
    for w in (blocked, free):
        failures[w["asset"]] = _id()
        args = {"a": w["asset"], "s": w["source"], "t": w["tenant"], "u": w["user"]}
        await _run(insert, id=failures[w["asset"]], r=1, st="failed", **args)
    await _run(
        insert, id=_id(), r=2, st="queued", a=blocked["asset"], s=blocked["source"], t=blocked["tenant"], u=blocked["user"]
    )
    # Exclude every other test's failures, so only these two are candidates.
    others = {
        row
        for row in (await _rows("SELECT id FROM content_ingestion_jobs WHERE status = 'failed'"))
        if row not in failures.values()
    }
    for _ in range(6):  # past five runs
        async with SessionLocal() as session, session.begin():
            claimed = await SqlAlchemyContentIngestionJobRepository(session).claim_next_retryable_failure(others)
        assert claimed is not None and claimed.id == failures[free["asset"]]


# --- The operator's reports (read-only) --------------------------------------------------------


async def test_the_reports_find_what_they_list_and_cannot_write():
    w, other = await _world(), await _world()
    # A document filed under another tenant's source: allowed until PR 8.
    mismatched = _id()
    await _run(
        "INSERT INTO content_assets (id, source_id, tenant_id, file_name, mime_type, file_size_bytes, content_sha256,"
        " storage_uri, asset_version, status, ingestion_status, metadata, created_by, created_by_email,"
        " created_at, updated_at)"
        " VALUES (:id, :s, :t, 'f', 'application/pdf', 1, :sha, 'k', 1, 'active', 'uploaded', '{}', :u, 'e', now(), now())",
        id=mismatched,
        s=other["source"],
        t=w["tenant"],
        sha=uuid4().hex + uuid4().hex,
        u=w["user"],
    )
    personal = await _asset(w, sha=uuid4().hex + uuid4().hex, owner=w["user"], cls="personal")
    deleted = await _asset(w, sha=uuid4().hex + uuid4().hex, status="deleted")
    try:
        unclassified = _script("report_unclassified_assets")
        assert unclassified.returncode == 1, unclassified.stderr[-2000:]
        line = next(row for row in unclassified.stdout.splitlines() if w["asset"] in row)
        assert line.split("\t") == [w["tenant"], w["asset"], w["source"], "yes", "active"]
        # A classified document and a deleted one aren't listed.
        assert personal not in unclassified.stdout and deleted not in unclassified.stdout

        mismatches = _script("report_source_tenant_mismatches")
        assert mismatches.returncode == 1, mismatches.stderr[-2000:]
        assert [w["asset"] in mismatches.stdout, mismatched in mismatches.stdout] == [False, True]
        line = next(row for row in mismatches.stdout.splitlines() if mismatched in row)
        assert line.split("\t") == [mismatched, w["tenant"], other["source"], other["tenant"]]

        conflicts = _script("report_active_job_conflicts")
        assert (conflicts.returncode, conflicts.stdout.strip()) == (0, "documents with more than one active job: none")
    finally:
        await _run("DELETE FROM content_assets WHERE id = :a", a=mismatched)

    # The transaction is read-only: a write through it is refused by PostgreSQL.
    with pytest.raises(DBAPIError, match="read-only transaction"):
        await _read_only_rows("DELETE FROM content_assets WHERE id = 'none'")


# --- The abort before any DDL (last: it moves the schema down and back up) ------------------


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "alembic", *args], capture_output=True, text=True, check=False)


def _script(name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", f"scripts.{name}"], capture_output=True, text=True, check=False)


async def test_duplicate_active_jobs_stop_the_migration_and_change_nothing():
    w = await _world()
    # 0029 can't hold what only 0030 allows (two owners of the same bytes, or a
    # deleted document's hash): its unique constraint would refuse them, so a
    # downgrade over them fails. Those rows come only from the tests above.
    await _run("DELETE FROM content_assets WHERE ownership_class = 'personal' OR status = 'deleted'")
    # A downgrade drops owner_user_id, so a private source couldn't pass
    # ck_content_sources_owner on the way back up.
    await _run("DELETE FROM content_sources WHERE visibility = 'private'")
    down = _alembic("downgrade", "0029")
    assert down.returncode == 0, down.stderr[-2000:]
    try:
        jobs = [_id(), _id()]
        for job in jobs:
            await _run(
                "INSERT INTO content_ingestion_jobs (id, asset_id, source_id, tenant_id, run_number, status, attempt_count,"
                " max_attempts, error_details, is_retryable, metrics, attempt_history, created_by, created_at, updated_at)"
                " VALUES (:id, :a, :s, :t, 1, 'queued', 1, 3, '{}', false, '{}', '[]', :u, now(), now())",
                id=job,
                a=w["asset"],
                s=w["source"],
                t=w["tenant"],
                u=w["user"],
            )
        # The read-only report finds the same conflict before anyone migrates.
        found = _script("report_active_job_conflicts")
        assert found.returncode == 1, found.stderr[-2000:]
        assert w["asset"] in found.stdout and all(job in found.stdout for job in jobs)
        up = _alembic("upgrade", "head")
        assert up.returncode != 0
        assert "migration 0030 stopped" in up.stderr and w["asset"] in up.stderr
        assert all(job in up.stderr for job in jobs)
        # Nothing changed: still at 0029, with the old constraint and no new table.
        assert await _scalar("SELECT version_num FROM alembic_version") == "0029"
        assert await _scalar("SELECT to_regclass('public.content_blobs')") is None
        assert await _scalar("SELECT count(*) FROM pg_constraint WHERE conname = 'uq_content_assets_tenant_hash'") == 1
        assert await _scalar("SELECT count(*) FROM content_ingestion_jobs WHERE asset_id = :a", a=w["asset"]) == 2
    finally:
        await _run("DELETE FROM content_ingestion_jobs WHERE asset_id = :a", a=w["asset"])
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr[-2000:]
