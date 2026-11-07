"""Malware scanning on real PostgreSQL (M3-D PR 6, ruling 7): new documents
are quarantined with a pending scan; the worker's verdict releases or rejects
them; a scanner failure leaves them quarantined; a stale attempt can't
overwrite a newer one's verdict; nothing unscanned or rejected gets a job."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

import app.worker as worker
from app.application.content.job_handlers import DocumentNotScannedError, require_scanned
from app.db.session import SessionLocal
from app.infrastructure.content.asset_repositories import SqlAlchemyContentAssetRepository
from app.infrastructure.content.clamav import ScannerUnavailable, Verdict
from app.infrastructure.content.scan_repository import SqlAlchemyScanRepository
from app.infrastructure.content.unit_of_work import ContentUnitOfWork
from app.infrastructure.db.models.content import ContentAssetModel, ContentScanModel
from pg_smoke.test_migration_0030 import _world

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.real_scanning]


class FakeScanner:
    def __init__(self, clean: bool = True, fails: bool = False) -> None:
        self.clean, self.fails, self.scanned = clean, fails, []

    async def scan(self, data: bytes) -> Verdict:
        self.scanned.append(data)
        if self.fails:
            raise ScannerUnavailable("SCANNER_UNREACHABLE")
        return Verdict(self.clean, None if self.clean else "Eicar-Test-Signature", "ClamAV 1.4.1", "27450")


class FakeStorage:
    async def get(self, key, *, expected_sha256, max_bytes):
        return b"%PDF-1.4 bytes"


async def new_document(w) -> str:
    """A document inserted the way every upload inserts one."""
    from app.domain.content.asset import ContentAsset

    tenant = w["tenant"]
    asset_id = str(uuid4())
    sha = uuid4().hex + uuid4().hex
    asset = ContentAsset.create(
        source_id=w["source"],
        tenant_id=tenant,
        file_name="notes.pdf",
        mime_type="application/pdf",
        file_size_bytes=14,
        content_sha256=sha,
        storage_uri=f"s3://{worker.settings.object_storage_bucket}/tenants/{tenant}/assets/{asset_id}/{sha}",
        created_by=w["user"],
        created_by_email="staff@example.com",
        asset_id=asset_id,
    )
    async with SessionLocal() as session, session.begin():
        await SqlAlchemyContentAssetRepository(session).insert_asset(asset)
    return asset_id


async def state(asset_id: str) -> tuple[str, str, int]:
    async with SessionLocal() as session:
        status = await session.scalar(select(ContentAssetModel.ingestion_status).where(ContentAssetModel.id == asset_id))
        verdict, attempts = (
            await session.execute(
                select(ContentScanModel.verdict, ContentScanModel.attempts).where(ContentScanModel.asset_id == asset_id)
            )
        ).one()
    return status, verdict, attempts


async def only(asset_id: str) -> None:
    """Only this document is due: other pending scans (this module's earlier
    tests) wait a day, so a pass claims this one."""
    async with SessionLocal() as session, session.begin():
        await session.execute(
            update(ContentScanModel)
            .where(ContentScanModel.asset_id != asset_id, ContentScanModel.verdict == "pending")
            .values(next_attempt_at=datetime.now(timezone.utc) + timedelta(days=1), lease_until=None)
        )


async def scan_with(scanner, monkeypatch, asset_id: str) -> None:
    await only(asset_id)
    monkeypatch.setattr(worker, "_scanner", lambda: scanner)
    monkeypatch.setattr(worker, "_scan_storage", lambda: FakeStorage())
    await worker.run_scan_pass()


async def refused_job(asset_id: str) -> str | None:
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            asset = await uow.assets.get_asset_by_id(asset_id)
            try:
                await require_scanned(uow, asset)
            except DocumentNotScannedError as exc:
                return exc.code
    return None


async def test_a_new_document_is_quarantined_with_a_pending_scan_and_gets_no_job():
    w = await _world()
    asset_id = await new_document(w)
    assert await state(asset_id) == ("quarantined", "pending", 0)
    assert await refused_job(asset_id) == "DOCUMENT_NOT_SCANNED"


async def test_a_clean_verdict_releases_the_document(monkeypatch):
    w = await _world()
    asset_id = await new_document(w)
    await scan_with(FakeScanner(clean=True), monkeypatch, asset_id)
    assert await state(asset_id) == ("uploaded", "accepted", 1)
    assert await refused_job(asset_id) is None


async def test_a_found_signature_rejects_it_for_good(monkeypatch):
    w = await _world()
    asset_id = await new_document(w)
    await scan_with(FakeScanner(clean=False), monkeypatch, asset_id)
    assert await state(asset_id) == ("rejected", "rejected", 1)
    assert await refused_job(asset_id) == "DOCUMENT_REJECTED"


async def test_a_scanner_failure_leaves_it_quarantined_and_tries_again_later(monkeypatch):
    w = await _world()
    asset_id = await new_document(w)
    scanner = FakeScanner(fails=True)
    await scan_with(scanner, monkeypatch, asset_id)
    await worker.run_scan_pass()  # backed off: not tried again yet
    assert len(scanner.scanned) == 1
    assert await state(asset_id) == ("quarantined", "pending", 1)
    assert await refused_job(asset_id) == "DOCUMENT_NOT_SCANNED"


async def test_without_a_scanner_nothing_is_accepted(monkeypatch):
    w = await _world()
    asset_id = await new_document(w)
    await scan_with(None, monkeypatch, asset_id)
    assert await state(asset_id) == ("quarantined", "pending", 1)


async def test_a_stale_attempt_cant_overwrite_a_newer_attempts_verdict():
    w = await _world()
    asset_id = await new_document(w)
    await only(asset_id)
    async with SessionLocal() as session, session.begin():
        first = await SqlAlchemyScanRepository(session).claim_due(lease_seconds=60)
    assert first is not None and first.asset_id == asset_id
    # The first attempt's lease lapses and a second attempt takes the scan.
    async with SessionLocal() as session, session.begin():
        await session.execute(update(ContentScanModel).where(ContentScanModel.asset_id == asset_id).values(lease_until=None))
    async with SessionLocal() as session, session.begin():
        second = await SqlAlchemyScanRepository(session).claim_due(lease_seconds=60)
    assert second is not None and second.fence == first.fence + 1
    async with SessionLocal() as session, session.begin():
        assert await SqlAlchemyScanRepository(session).record_verdict(
            second, accepted=False, scanner="ClamAV 1.4.1", signature_version="27450"
        )
    # The stale first attempt's clean verdict changes nothing.
    async with SessionLocal() as session, session.begin():
        assert not await SqlAlchemyScanRepository(session).record_verdict(
            first, accepted=True, scanner="ClamAV 1.4.1", signature_version="27450"
        )
    assert (await state(asset_id))[:2] == ("rejected", "rejected")
