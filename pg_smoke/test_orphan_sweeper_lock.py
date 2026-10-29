from sqlalchemy import text

from app.db.session import engine
from app.domain.content.storage import ObjectStoragePage
from app.infrastructure.content.orphan_sweeper import (
    LOCK_CLASS_ID,
    LOCK_OBJECT_ID,
    sweep_orphaned_objects,
)


class EmptyStorage:
    def __init__(self):
        self.list_calls = 0

    async def list_page(self, *, prefix, continuation_token=None, max_keys=1000):
        self.list_calls += 1
        return ObjectStoragePage(objects=(), continuation_token=None)


async def test_orphan_sweep_advisory_lock_allows_only_one_process():
    storage = EmptyStorage()
    async with engine.connect() as first:
        acquired = await first.scalar(
            text("SELECT pg_try_advisory_lock(:class_id, :object_id)"),
            {"class_id": LOCK_CLASS_ID, "object_id": LOCK_OBJECT_ID},
        )
        await first.commit()
        assert acquired is True

        skipped = await sweep_orphaned_objects(storage, bucket="build-documents")

        assert skipped.lock_acquired is False
        assert storage.list_calls == 0

        unlocked = await first.scalar(
            text("SELECT pg_advisory_unlock(:class_id, :object_id)"),
            {"class_id": LOCK_CLASS_ID, "object_id": LOCK_OBJECT_ID},
        )
        await first.commit()
        assert unlocked is True

        acquired = await sweep_orphaned_objects(storage, bucket="build-documents")

    assert acquired.lock_acquired is True
    assert storage.list_calls == 1
