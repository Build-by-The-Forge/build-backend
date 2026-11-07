"""A stand-in for the scan worker, for tests whose subject is something else.

Every new document is quarantined with a pending scan, and nothing processes
it until a verdict accepts it (M3-D PR 6). The test environment has no
clamd, so tests that upload a document and then work with it would never get
past quarantine. This stand-in records the verdict the scan worker would
record for a clean file, in the same transaction that creates the pending
scan. Production code and the gate are unchanged: the stand-in only answers
the scan.

Tests about scanning itself are marked ``real_scanning`` and get the real
behaviour: the document stays quarantined until the worker's pass records a
verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import update


def scanner_accepts_new_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.content.scan_repository import SqlAlchemyScanRepository
    from app.infrastructure.db.models.content import ContentAssetModel, ContentScanModel

    original = SqlAlchemyScanRepository.create_pending

    async def accepted(self, tenant_id: str, asset_id: str) -> None:
        await original(self, tenant_id, asset_id)
        await self._session.execute(
            update(ContentScanModel)
            .where(ContentScanModel.asset_id == asset_id)
            .values(
                verdict="accepted",
                scanner="test stand-in",
                signature_version="0",
                scanned_at=datetime.now(timezone.utc),
                next_attempt_at=None,
            )
        )
        await self._session.execute(
            update(ContentAssetModel)
            .where(ContentAssetModel.id == asset_id, ContentAssetModel.ingestion_status == "quarantined")
            .values(ingestion_status="uploaded")
        )

    monkeypatch.setattr(SqlAlchemyScanRepository, "create_pending", accepted)


def stand_in_unless_real_scanning(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("real_scanning") is None:
        scanner_accepts_new_documents(monkeypatch)
