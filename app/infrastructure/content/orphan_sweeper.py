from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.content.upload import managed_storage_key
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.db.timeouts import set_transaction_timeouts
from app.domain.content.asset import ContentAsset
from app.domain.content.storage import ObjectStorage
from app.infrastructure.content.asset_repositories import SqlAlchemyContentAssetRepository

logger = structlog.get_logger(__name__)
OBJECT_PREFIX = "tenants/"
PAGE_SIZE = 1000
LOCK_CLASS_ID = 1_112_893_772
LOCK_OBJECT_ID = 1_330_790_472
_MANAGED_KEY = re.compile(r"^tenants/([^/]+)/assets/([^/]+)/([0-9a-f]{64})$")


@dataclass(slots=True)
class OrphanSweepSummary:
    lock_acquired: bool = True
    pages: int = 0
    scanned: int = 0
    deleted: int = 0
    kept: int = 0
    unparseable: int = 0


AssetLookup = Callable[[set[str]], Awaitable[list[ContentAsset]]]


def parse_managed_object_key(key: str) -> tuple[str, str] | None:
    match = _MANAGED_KEY.fullmatch(key)
    if match is None:
        return None
    return match.group(1), match.group(2)


async def sweep_object_pages(
    storage: ObjectStorage,
    asset_lookup: AssetLookup,
    *,
    bucket: str,
    grace_period_seconds: int,
    now: datetime | None = None,
) -> OrphanSweepSummary:
    if grace_period_seconds < 3600:
        raise ValueError("grace_period_seconds must be at least one hour")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    cutoff = current_time - timedelta(seconds=grace_period_seconds)
    summary = OrphanSweepSummary()
    token: str | None = None
    seen_tokens: set[str] = set()

    while True:
        page = await storage.list_page(prefix=OBJECT_PREFIX, continuation_token=token, max_keys=PAGE_SIZE)
        summary.pages += 1
        parsed = {item.key: parse_managed_object_key(item.key) for item in page.objects}
        asset_ids = {asset_id for parsed_key in parsed.values() if parsed_key for asset_id in [parsed_key[1]]}
        assets = {asset.id: asset for asset in await asset_lookup(asset_ids)} if asset_ids else {}

        for item in page.objects:
            summary.scanned += 1
            parsed_key = parsed[item.key]
            if parsed_key is None:
                summary.unparseable += 1
                summary.kept += 1
                logger.warning("orphan_object_kept", reason="unparseable_key")
                continue

            tenant_id, asset_id = parsed_key
            asset = assets.get(asset_id)
            if asset is not None and asset.tenant_id == tenant_id and managed_storage_key(asset, bucket) == item.key:
                summary.kept += 1
                continue

            if item.last_modified.tzinfo is None or item.last_modified.utcoffset() is None:
                raise ValueError("object storage returned a timezone-naive LastModified value")
            if item.last_modified >= cutoff:
                summary.kept += 1
                logger.info("orphan_object_kept", reason="within_grace_period")
                continue

            await storage.delete(item.key)
            summary.deleted += 1
            reason = "asset_missing" if asset is None else "asset_reference_mismatch"
            logger.info("orphan_object_deleted", reason=reason)

        next_token = page.continuation_token
        if next_token is None:
            break
        if next_token in seen_tokens or next_token == token:
            raise RuntimeError("object storage repeated a continuation token")
        seen_tokens.add(next_token)
        token = next_token

    return summary


async def sweep_orphaned_objects(
    storage: ObjectStorage,
    *,
    bucket: str,
    grace_period_seconds: int | None = None,
    now: datetime | None = None,
    database_engine: AsyncEngine = engine,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> OrphanSweepSummary:
    grace = settings.worker_orphan_grace_seconds if grace_period_seconds is None else grace_period_seconds
    async with database_engine.connect() as connection:
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:class_id, :object_id)"),
            {"class_id": LOCK_CLASS_ID, "object_id": LOCK_OBJECT_ID},
        )
        await connection.commit()
        if not acquired:
            logger.info("orphan_sweep_skipped", reason="another_sweeper_holds_lock")
            return OrphanSweepSummary(lock_acquired=False)

        async def lookup(asset_ids: set[str]) -> list[ContentAsset]:
            async with session_factory() as session:
                await set_transaction_timeouts(session)
                return await SqlAlchemyContentAssetRepository(session).get_assets_by_ids(asset_ids)

        try:
            summary = await sweep_object_pages(
                storage,
                lookup,
                bucket=bucket,
                grace_period_seconds=grace,
                now=now,
            )
            logger.info(
                "orphan_sweep_completed",
                pages=summary.pages,
                scanned=summary.scanned,
                deleted=summary.deleted,
                kept=summary.kept,
                unparseable=summary.unparseable,
            )
            return summary
        finally:
            unlocked = await connection.scalar(
                text("SELECT pg_advisory_unlock(:class_id, :object_id)"),
                {"class_id": LOCK_CLASS_ID, "object_id": LOCK_OBJECT_ID},
            )
            await connection.commit()
            if not unlocked:
                raise RuntimeError("orphan sweeper lost its PostgreSQL advisory lock")
