"""Who may read a document or its job: one policy (M3-D ruling B).

Every route that lists, returns or streams a document or its ingestion job
goes through ``ContentReadService``, staff routes included. The rules are
here, as ``may_read``. Lists and single reads apply them in SQL, through the
``ContentReadPort`` the infrastructure implements. A test checks that the SQL
and ``may_read`` agree on every row of the design's table
(docs/m3-d-design.md, "Reading"), so they can't drift apart, and another
fails on any ``/content`` route that doesn't take a ``Reader``.

| Document | Owner | Another student | Content staff | Another tenant |
|---|---|---|---|---|
| Personal, private | yes | no | no | no |
| Personal, published and clean | yes | yes | yes | no |
| Institutional, not reviewed for students | - | no | yes | no |
| Institutional, reviewed for students | - | yes | yes | no |
| Unclassified | - | no | yes, on the staff routes | no |
| Revoked or deleted | no | no | no | no |

- **Content staff** means a caller who manages shared material
  (``content.source.manage``). That is never access to a student's private
  documents.
- **Reviewed for students:** the document's latest staff review accepted it
  for the audience ``tenant``. Narrower audiences (faculty, department,
  programme, course) stay staff-only until the backend records a student's
  place in them (G-28), so they fail closed.
- **Published:** a live publication in state ``published`` that isn't hidden.
- **Platform documents** (no tenant) are for content staff only: they carry
  no rights review for students.
- **Unclassified** documents are every document from before M3-D and every
  new staff upload until it's classified. Students never see them. Content
  staff keep reaching them on the existing staff routes, so staff upload
  and ingestion keep working while classification happens (PR 5).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, IngestionStatus
from app.domain.content.job import ContentIngestionJob

# Statuses no one may read through any route.
UNREADABLE_STATUSES = frozenset({AssetStatus.REVOKED.value, "deleted"})
# Scan outcomes that keep a published document off everyone else's reads.
UNCLEAN_INGESTION = frozenset({"quarantined", "rejected"})


@dataclass(frozen=True, slots=True)
class Reader:
    """Who is reading: their verified tenant, their user and whether they
    manage shared material. Built from the caller's TenantContext only."""

    tenant_id: str
    user_id: str
    manages_shared: bool


@dataclass(frozen=True, slots=True)
class DocumentFacts:
    """What the policy needs to know about one document."""

    tenant_id: str | None
    status: str
    ownership_class: str
    owner_user_id: str | None
    ingestion_status: str
    published: bool
    reviewed_for_students: bool


def may_read(document: DocumentFacts, reader: Reader) -> bool:
    if document.status in UNREADABLE_STATUSES:
        return False
    if document.tenant_id is None:
        return reader.manages_shared
    if document.tenant_id != reader.tenant_id:
        return False
    if document.ownership_class == "personal":
        if document.owner_user_id is not None and document.owner_user_id == reader.user_id:
            return True
        return document.published and document.ingestion_status not in UNCLEAN_INGESTION
    if document.ownership_class == "institutional":
        return reader.manages_shared or document.reviewed_for_students
    # unclassified, and anything this policy doesn't know: staff only
    return reader.manages_shared


class ContentReadPort(Protocol):
    """The policy in SQL. Each method applies exactly ``may_read``."""

    async def readable_asset_ids(self, reader: Reader, asset_ids: set[str]) -> set[str]: ...

    async def list_assets(
        self,
        reader: Reader,
        *,
        source_id: str | None,
        status: AssetStatus | None,
        ingestion_status: IngestionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContentAsset], int]: ...

    async def list_jobs(
        self,
        reader: Reader,
        *,
        asset_id: str | None,
        source_id: str | None,
        status: IngestionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContentIngestionJob], int]: ...

    async def get_job(self, reader: Reader, job_id: str) -> ContentIngestionJob | None: ...


class ContentReadService:
    """The one entry point for reading documents and jobs (ruling B)."""

    def __init__(self, port_factory: Callable[[], AbstractAsyncContextManager[ContentReadPort]]) -> None:
        self._port_factory = port_factory

    async def may_read_asset(self, reader: Reader, asset_id: str) -> bool:
        async with self._port_factory() as port:
            return asset_id in await port.readable_asset_ids(reader, {asset_id})

    async def readable_asset_ids(self, reader: Reader, asset_ids: set[str]) -> set[str]:
        if not asset_ids:
            return set()
        async with self._port_factory() as port:
            return await port.readable_asset_ids(reader, asset_ids)

    async def list_assets(
        self,
        reader: Reader,
        *,
        source_id: str | None = None,
        status: AssetStatus | None = None,
        ingestion_status: IngestionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentAsset], int]:
        async with self._port_factory() as port:
            return await port.list_assets(
                reader, source_id=source_id, status=status, ingestion_status=ingestion_status, limit=limit, offset=offset
            )

    async def list_jobs(
        self,
        reader: Reader,
        *,
        asset_id: str | None = None,
        source_id: str | None = None,
        status: IngestionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentIngestionJob], int]:
        async with self._port_factory() as port:
            return await port.list_jobs(reader, asset_id=asset_id, source_id=source_id, status=status, limit=limit, offset=offset)

    async def get_job(self, reader: Reader, job_id: str) -> ContentIngestionJob | None:
        """The job if its document is readable, else None (a 404, whatever the reason)."""
        async with self._port_factory() as port:
            return await port.get_job(reader, job_id)
