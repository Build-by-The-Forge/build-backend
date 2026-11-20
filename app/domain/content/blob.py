"""A blob: the physical bytes that documents with the same SHA-256 share in
one tenant (M3-D, migration 0030). It holds no person, consent or
permission, which stay on each document.

Its object key is ``tenants/{tenant}/blobs/{sha256}/{generation}``. The
generation is a lowercase UUID chosen when the row is created, so a key is
never shared with an earlier row of the same bytes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BLOB_GENERATION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def blob_object_key(tenant_id: str, sha256: str, generation: str) -> str:
    return f"tenants/{tenant_id}/blobs/{sha256}/{generation}"


@dataclass(frozen=True, slots=True)
class ContentBlob:
    id: str
    tenant_id: str
    content_sha256: str
    generation: str
    object_key: str
    # pending, active or deleting.
    state: str
