"""The one read policy (M3-D ruling B): the design's table, and the SQL
predicate agreeing with ``may_read`` on every row of it, for every reader."""

import pytest

from app.application.content.read_policy import may_read
from app.infrastructure.content.read_policy_sql import content_read_port
from tests.integration.content.read_policy_world import build_world

READERS = ("owner", "student", "staff", "other_staff", "other_student")

# The design's table (docs/m3-d-design.md, "Reading"), one row per document,
# in READERS order.
EXPECTED = {
    "personal private": (True, False, False, False, False),
    "personal published": (True, True, True, False, False),
    "personal published, quarantined": (True, False, False, False, False),
    "personal published, rejected by the scan": (True, False, False, False, False),
    "personal published, hidden": (True, False, False, False, False),
    "personal, publication requested": (True, False, False, False, False),
    "personal deleted": (False, False, False, False, False),
    "personal revoked": (False, False, False, False, False),
    "institutional, not reviewed": (False, False, True, False, False),
    "institutional, reviewed for the tenant": (True, True, True, False, False),
    "institutional, reviewed for a course only": (False, False, True, False, False),
    "institutional, accepted then rejected": (False, False, True, False, False),
    "institutional, rejected then accepted": (True, True, True, False, False),
    "institutional, reviewed, revoked": (False, False, False, False, False),
    "institutional, superseded": (False, False, True, False, False),
    "unclassified": (False, False, True, False, False),
    "unclassified, revoked": (False, False, False, False, False),
    "platform": (False, False, True, True, False),
    "another tenant's, reviewed": (False, False, False, True, True),
    "another tenant's unclassified": (False, False, False, True, False),
}


@pytest.mark.asyncio
async def test_may_read_is_the_designs_table():
    world = await build_world()
    assert set(EXPECTED) == set(world.docs)
    actual = {name: tuple(may_read(doc.facts, world.readers[reader]) for reader in READERS) for name, doc in world.docs.items()}
    assert actual == EXPECTED


@pytest.mark.asyncio
async def test_the_sql_agrees_with_may_read_on_every_row_for_every_reader():
    world = await build_world()
    ids = set(world.assets.values())
    for reader_name in READERS:
        reader = world.readers[reader_name]
        async with content_read_port() as port:
            readable_ids = await port.readable_asset_ids(reader, ids)
        expected = {world.assets[name] for name, doc in world.docs.items() if may_read(doc.facts, reader)}
        names = {asset: name for name, asset in world.assets.items()}
        assert sorted(names[i] for i in readable_ids) == sorted(names[i] for i in expected), reader_name


@pytest.mark.asyncio
async def test_lists_and_their_totals_count_only_what_the_reader_may_read():
    world = await build_world(future_states=False)
    names = {asset: name for name, asset in world.assets.items()}
    for reader_name in READERS:
        reader = world.readers[reader_name]
        async with content_read_port() as port:
            listed, total = await port.list_assets(
                reader, source_id=None, status=None, ingestion_status=None, limit=100, offset=0
            )
        mine = sorted(names[a.id] for a in listed if a.id in names)
        expected = sorted(name for name, doc in world.docs.items() if may_read(doc.facts, reader))
        assert mine == expected, reader_name
        # Nothing else of this world's tenants is counted; platform documents
        # from other tests count for staff, as they're readable to them.
        assert total >= len(expected)
        if not reader.manages_shared:
            assert total == len(expected), reader_name
