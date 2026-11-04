"""Documents whose tenant differs from their source's (read-only).

    python -m scripts.report_source_tenant_mismatches

A clean result (exit code 0) is the precondition for making source_id
tenant-consistent (M3-D PR 8). A document without a tenant, under a source
with one, counts as a mismatch, and so does the reverse.
"""

from __future__ import annotations

import sys

from scripts._read_only_report import report

SQL = (
    "SELECT a.id, a.tenant_id, a.source_id, s.tenant_id"
    " FROM content_assets a JOIN content_sources s ON s.id = a.source_id"
    " WHERE a.tenant_id IS DISTINCT FROM s.tenant_id"
    " ORDER BY a.tenant_id NULLS FIRST, a.id"
)

if __name__ == "__main__":
    sys.exit(
        report(
            "documents whose tenant differs from their source's",
            SQL,
            ("asset_id", "asset_tenant_id", "source_id", "source_tenant_id"),
        )
    )
