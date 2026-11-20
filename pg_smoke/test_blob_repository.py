"""Reading a document's blob on real PostgreSQL (M3-D PR 7): the row comes
back only for its own tenant, and a document names it by tenant-scoped id."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.application.content.upload import managed_storage_key, storage_uri_for
from app.db.session import SessionLocal
from app.domain.content.blob import ContentBlob, blob_object_key
from app.infrastructure.content.blob_repository import SqlAlchemyBlobRepository
from app.infrastructure.db.models.content import ContentBlobModel
from tests.integration.content.test_classification import world

pytestmark = pytest.mark.asyncio(loop_scope="session")

SHA = "a" * 64
BUCKET = "build-documents"


async def make_blob(tenant_id: str, *, state: str = "active", sha: str = SHA) -> ContentBlobModel:
    generation = str(uuid4())
    model = ContentBlobModel(
        id=str(uuid4()),
        tenant_id=tenant_id,
        content_sha256=sha,
        size_bytes=10,
        mime_type="application/pdf",
        generation=generation,
        object_key=blob_object_key(tenant_id, sha, generation),
        state=state,
        claimed_until=datetime.now(timezone.utc) + timedelta(hours=1) if state == "pending" else None,
    )
    async with SessionLocal() as session:
        session.add(model)
        await session.commit()
    return model


async def test_a_blob_is_read_only_for_its_own_tenant():
    mine, theirs = await world(), await world()
    blob = await make_blob(mine["tenant"])

    async with SessionLocal() as session:
        repo = SqlAlchemyBlobRepository(session)
        for _ in range(7):  # past five runs, where a generic plan could differ
            found = await repo.get(mine["tenant"], blob.id)
            assert found is not None and found.object_key == blob.object_key
            assert await repo.get(theirs["tenant"], blob.id) is None
        assert await repo.get(mine["tenant"], str(uuid4())) is None


async def test_the_stored_blob_row_makes_its_documents_reference_managed():
    w = await world()
    blob = await make_blob(w["tenant"])
    async with SessionLocal() as session:
        found = await SqlAlchemyBlobRepository(session).get(w["tenant"], blob.id)
    assert isinstance(found, ContentBlob)

    from app.domain.content.asset import ContentAsset

    asset = ContentAsset.create(
        source_id="s",
        tenant_id=w["tenant"],
        file_name="n.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        content_sha256=SHA,
        storage_uri=storage_uri_for(BUCKET, blob.object_key),
        created_by="u",
        created_by_email="u@example.com",
    )
    asset.blob_id = blob.id
    assert managed_storage_key(asset, BUCKET, found) == blob.object_key

    # One live blob per hash in a tenant: the pending one holds other bytes.
    pending = await make_blob(w["tenant"], state="pending", sha="b" * 64)
    async with SessionLocal() as session:
        pending_row = await SqlAlchemyBlobRepository(session).get(w["tenant"], pending.id)
    assert managed_storage_key(asset, BUCKET, pending_row) is None

    # A second live blob for the same bytes is refused by the database.
    with pytest.raises(IntegrityError):
        await make_blob(w["tenant"])
