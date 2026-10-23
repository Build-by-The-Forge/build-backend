"""Concurrent uploads on PostgreSQL: the real constraints decide the race.

Two requests are held inside ``put`` until both have passed the service's
pre-checks, then both insert. The loser's IntegrityError must be classified
from the committed rows: a primary-key collision (same Idempotency-Key) is a
replay or IDEMPOTENCY_KEY_REUSED; a uq_content_assets_tenant_hash collision
(same bytes, another key) is DUPLICATE_CONTENT. The loser leaves no object
behind unless the winner's row references it.
"""

import asyncio
import hashlib
import io
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.content.upload import (
    SIGNATURE_BYTES,
    ContentAssetUploadService,
    DuplicateContentError,
    IdempotencyKeyReusedError,
    UploadedBody,
)
from app.bootstrap.container import sqlalchemy_content_uow
from app.db.session import SessionLocal
from app.domain.content.enums import AuthorityLevel, ContentSourceType, VisibilityScope
from app.domain.content.source import ContentSource
from app.domain.content.storage import ObjectInfo, ObjectNotFoundError, StoredObject
from app.infrastructure.db.models.content import ContentAssetModel
from app.infrastructure.db.models.tenant_core import TenantModel

pytestmark = pytest.mark.asyncio(loop_scope="session")

PDF = b"%PDF-1.7\n" + b"race notes " * 200
OTHER_PDF = b"%PDF-1.7\n" + b"other race notes " * 200


class BarrierStorage:
    """In-memory storage whose put waits until ``parties`` puts arrived, so
    every racer has passed the pre-checks before any of them inserts."""

    def __init__(self, parties: int = 2) -> None:
        self.objects: dict[str, bytes] = {}
        self._parties = parties
        self._arrived = 0
        self._all_arrived = asyncio.Event()

    async def put(self, key, data, *, content_type, expected_sha256=None):
        raw = data.read()
        self.objects[key] = raw
        self._arrived += 1
        if self._arrived >= self._parties:
            self._all_arrived.set()
        await asyncio.wait_for(self._all_arrived.wait(), timeout=10)
        return StoredObject(key=key, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), content_type=content_type)

    async def get(self, key, *, expected_sha256, max_bytes):
        raise NotImplementedError

    async def head(self, key):
        if key not in self.objects:
            raise ObjectNotFoundError("missing")
        raw = self.objects[key]
        return ObjectInfo(key=key, size_bytes=len(raw), content_type=None, sha256=hashlib.sha256(raw).hexdigest())

    async def delete(self, key):
        self.objects.pop(key, None)


async def _tenant_and_source() -> tuple[str, ContentSource]:
    now = datetime.now(timezone.utc)
    tenant_id, tag = str(uuid4()), uuid4().hex[:8]
    async with SessionLocal() as session:
        session.add(TenantModel(id=tenant_id, name="Race", slug=f"race-{tag}", status="active", created_at=now, updated_at=now))
        await session.commit()
    source = ContentSource.create(
        code=f"RACE_{tag.upper()}",
        name="Race notes",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-race",
        created_by_email="usr-race@build.internal",
        tenant_id=tenant_id,
    )
    async with sqlalchemy_content_uow() as uow:
        await uow.sources.save_source(source)
    return tenant_id, source


def _body(data: bytes) -> UploadedBody:
    return UploadedBody(
        file=io.BytesIO(data), size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), head=data[:SIGNATURE_BYTES]
    )


async def _race(uploads: list[tuple[str, bytes]]):
    tenant_id, source = await _tenant_and_source()
    storage = BarrierStorage(parties=len(uploads))
    service = ContentAssetUploadService(
        uow_factory=sqlalchemy_content_uow, storage_factory=lambda: storage, bucket=lambda: "build-documents"
    )

    async def one(key: str, data: bytes):
        return await service.upload(
            source_id=source.id,
            tenant_id=tenant_id,
            user_id="usr-race",
            user_email="usr-race@build.internal",
            file_name="notes.pdf",
            idempotency_key=key,
            body=_body(data),
            correlation_id=None,
        )

    outcomes = await asyncio.gather(*(one(key, data) for key, data in uploads), return_exceptions=True)
    async with SessionLocal() as session:
        rows = (await session.execute(select(ContentAssetModel).where(ContentAssetModel.tenant_id == tenant_id))).scalars().all()
    return outcomes, rows, storage


def _key_of(storage_uri: str) -> str:
    return storage_uri.split("/", 3)[3]


async def test_the_same_key_and_bytes_racing_yield_one_asset_and_keep_its_object():
    outcomes, rows, storage = await _race([("k-same", PDF), ("k-same", PDF)])

    assert not any(isinstance(o, BaseException) for o in outcomes), outcomes
    assert sorted(o.created for o in outcomes) == [False, True]
    assert {o.asset.id for o in outcomes} == {rows[0].id}
    assert len(rows) == 1
    assert set(storage.objects) == {_key_of(rows[0].storage_uri)}


async def test_the_same_key_with_other_bytes_racing_is_key_reuse_without_an_orphan():
    outcomes, rows, storage = await _race([("k-reused", PDF), ("k-reused", OTHER_PDF)])

    errors = [o for o in outcomes if isinstance(o, BaseException)]
    winners = [o for o in outcomes if not isinstance(o, BaseException)]
    assert len(winners) == 1 and winners[0].created
    assert len(errors) == 1 and isinstance(errors[0], IdempotencyKeyReusedError), errors
    assert len(rows) == 1
    assert set(storage.objects) == {_key_of(rows[0].storage_uri)}  # the loser's object was deleted


async def test_the_same_bytes_under_two_keys_racing_is_duplicate_content_without_an_orphan():
    outcomes, rows, storage = await _race([("k-one", PDF), ("k-two", PDF)])

    errors = [o for o in outcomes if isinstance(o, BaseException)]
    winners = [o for o in outcomes if not isinstance(o, BaseException)]
    assert len(winners) == 1 and winners[0].created
    assert len(errors) == 1 and isinstance(errors[0], DuplicateContentError), errors
    assert errors[0].existing_asset_id == winners[0].asset.id == rows[0].id
    assert len(rows) == 1
    assert set(storage.objects) == {_key_of(rows[0].storage_uri)}
