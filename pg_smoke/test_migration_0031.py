"""Migration 0031 on real PostgreSQL (M3-D PR 5): the tenant authority record,
operator runs, and the scope-assignment outbox's rules."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from pg_smoke.test_migration_0030 import REFUSED, _id, _refused, _run, _scalar, _world

pytestmark = pytest.mark.asyncio(loop_scope="session")

NOW = datetime.now(timezone.utc)


async def _authorization(w, **overrides) -> str:
    values = {
        "id": _id(),
        "t": w["tenant"],
        "name": "Registrar",
        "role": "Registrar",
        "granted": NOW - timedelta(days=1),
        "covers": "Classify existing lecture notes as institutional",
        "doc": "REG/2026/014",
        "u": w["user"],
        "expires": None,
    }
    values.update(overrides)
    await _run(
        "INSERT INTO content_authority_authorizations (id, tenant_id, authority_name, authority_role, granted_at,"
        " covers, document_reference, recorded_by, expires_at)"
        " VALUES (:id, :t, :name, :role, :granted, :covers, :doc, :u, :expires)",
        **values,
    )
    return values["id"]


async def _assignment(w, *, version: int, scope: str = "institutional", lowers: bool | None = None, **extra) -> str:
    row = _id()
    await _run(
        "INSERT INTO content_scope_assignments (id, tenant_id, asset_id, scope, version, lowers, reason, decided_by)"
        " VALUES (:id, :t, :a, :s, :v, :l, 'test', :u)",
        id=row,
        t=extra.get("tenant", w["tenant"]),
        a=extra.get("asset", w["asset"]),
        s=scope,
        v=version,
        l=(scope != "institutional") if lowers is None else lowers,
        u=w["user"],
    )
    return row


async def test_an_authorization_needs_its_authority_scope_document_and_a_coherent_revocation():
    w = await _world()
    await _authorization(w)
    for field in ("name", "role", "covers", "doc"):
        with pytest.raises(REFUSED):
            await _authorization(w, **{field: " "})
    with pytest.raises(REFUSED):
        await _authorization(w, expires=NOW - timedelta(days=2))  # expires before it was granted
    await _refused(
        "UPDATE content_authority_authorizations SET revoked_at = now() WHERE tenant_id = :t", t=w["tenant"]
    )  # revoked without saying by whom


async def test_a_run_names_an_authorization_of_its_own_tenant():
    w, other = await _world(), await _world()
    theirs = await _authorization(other)
    insert = (
        "INSERT INTO content_classification_runs (id, tenant_id, authorization_id, operator_user_id, requested)"
        " VALUES (:id, :t, :auth, :u, 1)"
    )
    await _refused(insert, id=_id(), t=w["tenant"], auth=theirs, u=w["user"])
    mine = await _authorization(w)
    await _refused(insert.replace("1)", "0)"), id=_id(), t=w["tenant"], auth=mine, u=w["user"])  # an empty run
    await _run(insert, id=_id(), t=w["tenant"], auth=mine, u=w["user"])


async def test_an_operator_classification_names_a_run_of_its_own_tenant():
    w, other = await _world(), await _world()
    run = _id()
    await _run(
        "INSERT INTO content_classification_runs (id, tenant_id, authorization_id, operator_user_id, requested)"
        " VALUES (:id, :t, :auth, :u, 1)",
        id=run,
        t=other["tenant"],
        auth=await _authorization(other),
        u=other["user"],
    )
    insert = (
        "INSERT INTO content_ownership_classifications (id, tenant_id, asset_id, previous_class, new_class, decided_by,"
        " decided_via, evidence_reference, run_id) VALUES (:id, :t, :a, 'unclassified', 'institutional', :u,"
        " 'operator_command', 'REG/2026/014 item 3', :run)"
    )
    # Another tenant's run, or a run that doesn't exist, is refused.
    await _refused(insert, id=_id(), t=w["tenant"], a=w["asset"], u=w["user"], run=run)
    await _refused(insert, id=_id(), t=w["tenant"], a=w["asset"], u=w["user"], run=str(uuid4()))


async def test_assignment_versions_rise_per_document_and_lowering_matches_scope():
    w = await _world()
    await _assignment(w, version=1)
    with pytest.raises(REFUSED):
        await _assignment(w, version=1)  # one row per version
    with pytest.raises(REFUSED):
        await _assignment(w, version=0)
    with pytest.raises(REFUSED):
        await _assignment(w, version=2, scope="unknown", lowers=False)  # a lowering must say so
    with pytest.raises(REFUSED):
        await _assignment(w, version=2, scope="institutional", lowers=True)
    with pytest.raises(REFUSED):
        await _assignment(w, version=2, scope="public")
    await _assignment(w, version=2, scope="unknown")
    assert (
        await _scalar(
            "SELECT count(*) FROM content_scope_assignments WHERE tenant_id = :t AND asset_id = :a", t=w["tenant"], a=w["asset"]
        )
        == 2
    )


async def test_an_assignment_names_a_document_of_its_own_tenant():
    w, other = await _world(), await _world()
    with pytest.raises(REFUSED):
        await _assignment(w, version=1, asset=other["asset"])


async def test_settled_and_pending_states_are_consistent():
    w = await _world()
    row = await _assignment(w, version=1)
    await _refused("UPDATE content_scope_assignments SET state = 'acknowledged' WHERE id = :id", id=row)
    await _refused("UPDATE content_scope_assignments SET settled_at = now() WHERE id = :id", id=row)
    await _refused("UPDATE content_scope_assignments SET attempts = -1 WHERE id = :id", id=row)
    await _run("UPDATE content_scope_assignments SET state = 'acknowledged', settled_at = now() WHERE id = :id", id=row)


async def test_a_pending_lowering_keeps_its_document_and_a_tenant_cascade_removes_both():
    w = await _world()
    await _assignment(w, version=1, scope="unknown")
    # The document can't be deleted while an assignment names it.
    await _refused("DELETE FROM content_assets WHERE id = :a", a=w["asset"])
    await _run("DELETE FROM tenants WHERE id = :t", t=w["tenant"])
    assert await _scalar("SELECT count(*) FROM content_scope_assignments WHERE tenant_id = :t", t=w["tenant"]) == 0
