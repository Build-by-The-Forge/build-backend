"""Document scans (M3-D PR 6, ruling 7), on 0030's ``content_scans``.

- Every new document gets a pending scan in the transaction that inserts it,
  and stays ``quarantined`` until a verdict accepts it.
- A scan attempt claims the row with a lease and takes a new fence. Its
  verdict is recorded only if it still holds that fence and the row is still
  pending, so an attempt whose lease expired and was replaced can't
  overwrite the newer attempt's verdict.
- The verdict and the document's status change in one transaction: accepted
  moves ``quarantined`` to ``uploaded``; rejected moves it to ``rejected``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.content.enums import IngestionStatus
from app.infrastructure.db.models.content import ContentAssetModel, ContentScanModel


@dataclass(frozen=True, slots=True)
class ScanClaim:
    asset_id: str
    tenant_id: str
    fence: int
    attempts: int
    storage_uri: str
    content_sha256: str
    file_size_bytes: int


class SqlAlchemyScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(self, tenant_id: str, asset_id: str) -> None:
        self._session.add(
            ContentScanModel(
                asset_id=asset_id,
                tenant_id=tenant_id,
                verdict="pending",
                fence=0,
                attempts=0,
                next_attempt_at=datetime.now(timezone.utc),
            )
        )
        await self._session.flush()

    async def verdict(self, asset_id: str) -> str | None:
        """The document's scan verdict; None if it has never had a scan."""
        return await self._session.scalar(select(ContentScanModel.verdict).where(ContentScanModel.asset_id == asset_id))

    async def claim_due(self, lease_seconds: int) -> ScanClaim | None:
        """Take the next due pending scan whose lease has lapsed: a new fence
        and a lease, committed by the caller before the scan runs."""
        now = datetime.now(timezone.utc)
        row = (
            await self._session.execute(
                select(ContentScanModel, ContentAssetModel)
                .join(
                    ContentAssetModel,
                    (ContentAssetModel.id == ContentScanModel.asset_id)
                    & (ContentAssetModel.tenant_id == ContentScanModel.tenant_id),
                )
                .where(
                    ContentScanModel.verdict == "pending",
                    (ContentScanModel.next_attempt_at.is_(None)) | (ContentScanModel.next_attempt_at <= now),
                    (ContentScanModel.lease_until.is_(None)) | (ContentScanModel.lease_until <= now),
                )
                .order_by(ContentScanModel.next_attempt_at.asc().nulls_first(), ContentScanModel.asset_id.asc())
                .limit(1)
                .with_for_update(of=ContentScanModel, skip_locked=True)
            )
        ).first()
        if row is None:
            return None
        scan, asset = row
        scan.fence = scan.fence + 1
        scan.attempts = scan.attempts + 1
        scan.lease_until = now + timedelta(seconds=lease_seconds)
        await self._session.flush()
        return ScanClaim(
            asset_id=scan.asset_id,
            tenant_id=scan.tenant_id,
            fence=scan.fence,
            attempts=scan.attempts,
            storage_uri=asset.storage_uri,
            content_sha256=asset.content_sha256,
            file_size_bytes=asset.file_size_bytes,
        )

    async def record_verdict(self, claim: ScanClaim, *, accepted: bool, scanner: str, signature_version: str) -> bool:
        """Record the verdict if this attempt still holds the scan; then move
        the document out of quarantine. False if a newer attempt holds it."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            update(ContentScanModel)
            .where(
                ContentScanModel.asset_id == claim.asset_id,
                ContentScanModel.fence == claim.fence,
                ContentScanModel.verdict == "pending",
            )
            .values(
                verdict="accepted" if accepted else "rejected",
                scanner=scanner,
                signature_version=signature_version,
                scanned_at=now,
                lease_until=None,
                next_attempt_at=None,
            )
        )
        if result.rowcount != 1:
            return False
        await self._session.execute(
            update(ContentAssetModel)
            .where(
                ContentAssetModel.id == claim.asset_id,
                ContentAssetModel.ingestion_status == IngestionStatus.QUARANTINED.value,
            )
            .values(
                ingestion_status=(IngestionStatus.UPLOADED if accepted else IngestionStatus.REJECTED).value,
                updated_at=now,
            )
        )
        return True

    async def defer(self, claim: ScanClaim, delay_seconds: int) -> None:
        """No verdict: the document stays quarantined and is tried again later."""
        await self._session.execute(
            update(ContentScanModel)
            .where(
                ContentScanModel.asset_id == claim.asset_id,
                ContentScanModel.fence == claim.fence,
                ContentScanModel.verdict == "pending",
            )
            .values(lease_until=None, next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds))
        )
