"""Concurrent versions on PostgreSQL: the conditional supersede decides
(P3-1 PR 3b, design section 9).

Both requests are held inside ``put`` until each has passed every
pre-check, so both reach the transaction that supersedes the parent and
inserts the child. The row lock lets one through; the other must be
classified, leave no object behind, and leave exactly one current version.
"""

import asyncio
import hashlib
import io

import pytest
from sqlalchemy import select, update

from app.application.content.upload import (
    SIGNATURE_BYTES,
    AssetNotVersionableError,
    AssetVersionConflictError,
    ContentAssetUploadService,
    UploadedBody,
)
from app.bootstrap.container import sqlalchemy_content_uow
from app.db.session import SessionLocal
from app.infrastructure.db.models.content import ContentAssetModel
from pg_smoke.test_content_upload_race import BarrierStorage, _tenant_and_source

pytestmark = pytest.mark.asyncio(loop_scope="session")

PDF = b"%PDF-1.7\n" + b"edition one " * 200
V2 = b"%PDF-1.7\n" + b"edition two " * 200
V2B = b"%PDF-1.7\n" + b"edition two, other draft " * 200


def _body(data: bytes) -> UploadedBody:
    return UploadedBody(
        file=io.BytesIO(data), size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), head=data[:SIGNATURE_BYTES]
    )


async def _parent(tenant_id, source):
    service = ContentAssetUploadService(
        uow_factory=sqlalchemy_content_uow, storage_factory=lambda: BarrierStorage(parties=1), bucket=lambda: "build-documents"
    )
    result = await service.upload(
        source_id=source.id,
        tenant_id=tenant_id,
        user_id="usr-race",
        user_email="usr-race@build.internal",
        file_name="notes.pdf",
        idempotency_key="parent",
        body=_body(PDF),
    )
    return result.asset


async def _race(versions: list[tuple[str, bytes]], *, during_put=None):
    tenant_id, source = await _tenant_and_source()
    parent = await _parent(tenant_id, source)
    storage = BarrierStorage(parties=len(versions))
    if during_put is not None:
        real_put = storage.put

        async def put_then(key, data, **kwargs):
            stored = await real_put(key, data, **kwargs)
            await during_put(parent)
            return stored

        storage.put = put_then
    service = ContentAssetUploadService(
        uow_factory=sqlalchemy_content_uow, storage_factory=lambda: storage, bucket=lambda: "build-documents"
    )

    async def one(key: str, data: bytes):
        return await service.upload_version(
            parent_asset_id=parent.id,
            tenant_id=tenant_id,
            user_id="usr-race",
            user_email="usr-race@build.internal",
            file_name="notes-v2.pdf",
            idempotency_key=key,
            body=_body(data),
        )

    outcomes = await asyncio.gather(*(one(key, data) for key, data in versions), return_exceptions=True)
    async with SessionLocal() as session:
        rows = (await session.execute(select(ContentAssetModel).where(ContentAssetModel.tenant_id == tenant_id))).scalars().all()
    return parent, outcomes, rows, storage


def _key_of(storage_uri: str) -> str:
    return storage_uri.split("/", 3)[3]


async def test_two_versions_of_one_parent_racing_leave_one_current_version():
    parent, outcomes, rows, storage = await _race([("v-a", V2), ("v-b", V2B)])

    winners = [o for o in outcomes if not isinstance(o, BaseException)]
    errors = [o for o in outcomes if isinstance(o, BaseException)]
    assert len(winners) == 1 and winners[0].created, outcomes
    assert len(errors) == 1 and isinstance(errors[0], AssetVersionConflictError), errors
    by_id = {row.id: row for row in rows}
    assert by_id[parent.id].status == "superseded"
    active = [row for row in rows if row.status == "active"]
    assert [row.id for row in active] == [winners[0].asset.id]  # exactly one current version
    children = {_key_of(row.storage_uri) for row in rows if row.id != parent.id}
    assert set(storage.objects) == children  # the loser left no object (the parent's is in another store)


async def test_the_same_version_request_racing_with_itself_is_one_transition():
    parent, outcomes, rows, storage = await _race([("v-same", V2), ("v-same", V2)])

    assert not any(isinstance(o, BaseException) for o in outcomes), outcomes
    assert sorted(o.created for o in outcomes) == [False, True]
    assert len({o.asset.id for o in outcomes}) == 1
    assert len(rows) == 2  # the parent and one child
    assert set(storage.objects) == {_key_of(row.storage_uri) for row in rows if row.id != parent.id}


async def test_a_parent_revoked_while_its_version_is_stored_is_not_superseded():
    async def revoke(parent):
        async with SessionLocal() as session:
            await session.execute(update(ContentAssetModel).where(ContentAssetModel.id == parent.id).values(status="revoked"))
            await session.commit()

    parent, outcomes, rows, storage = await _race([("v-late", V2)], during_put=revoke)

    assert isinstance(outcomes[0], AssetNotVersionableError), outcomes
    assert [row.status for row in rows] == ["revoked"]  # no active child of a revoked parent
    assert storage.objects == {}  # the version's object was compensated
