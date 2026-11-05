"""The read policy's SQL on real PostgreSQL (M3-D PR 4): it agrees with
may_read on every row of the design's table, past five runs, where a cached
generic plan could differ."""

import pytest

from app.application.content.read_policy import may_read
from app.infrastructure.content.read_policy_sql import content_read_port
from tests.integration.content.read_policy_world import build_world
from tests.integration.content.test_read_policy import EXPECTED, READERS

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_the_sql_agrees_with_may_read_on_postgresql_past_five_runs():
    world = await build_world()
    names = {asset: name for name, asset in world.assets.items()}
    ids = set(world.assets.values())
    for _ in range(6):
        for reader_name in READERS:
            reader = world.readers[reader_name]
            async with content_read_port() as port:
                readable_ids = await port.readable_asset_ids(reader, ids)
            expected = sorted(name for name, doc in world.docs.items() if may_read(doc.facts, reader))
            assert sorted(names[i] for i in readable_ids) == expected, reader_name
    # And may_read is still the design's table.
    assert {name: tuple(may_read(doc.facts, world.readers[r]) for r in READERS) for name, doc in world.docs.items()} == EXPECTED


async def test_lists_on_postgresql_count_only_what_the_reader_may_read():
    world = await build_world(future_states=False)
    names = {asset: name for name, asset in world.assets.items()}
    for reader_name in READERS:
        reader = world.readers[reader_name]
        async with content_read_port() as port:
            listed, total = await port.list_assets(
                reader, source_id=None, status=None, ingestion_status=None, limit=100, offset=0
            )
            jobs, job_total = await port.list_jobs(reader, asset_id=None, source_id=None, status=None, limit=100, offset=0)
        expected = sorted(name for name, doc in world.docs.items() if may_read(doc.facts, reader))
        assert sorted(names[a.id] for a in listed if a.id in names) == expected, reader_name
        if not reader.manages_shared:
            assert total == len(expected), reader_name
