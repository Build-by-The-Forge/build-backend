"""Unclassified documents, per tenant (read-only). Needs migration 0030.

    python -m scripts.report_unclassified_assets

The operator's starting list for classification (M3-D PR 5). For each
document: its source, and whether that is a staff source, meaning one with
no owner. That's evidence for the operator, never a default: nothing here
classifies anything. Deleted documents are left out.
"""

from __future__ import annotations

import sys

from scripts._read_only_report import report

SQL = (
    "SELECT a.tenant_id, a.id, a.source_id,"
    " CASE WHEN s.id IS NULL THEN 'missing' WHEN s.owner_user_id IS NULL THEN 'yes' ELSE 'no' END,"
    " a.status"
    " FROM content_assets a LEFT JOIN content_sources s ON s.id = a.source_id"
    " WHERE a.ownership_class = 'unclassified' AND a.status <> 'deleted'"
    " ORDER BY a.tenant_id NULLS FIRST, a.source_id, a.id"
)

if __name__ == "__main__":
    sys.exit(
        report(
            "unclassified documents",
            SQL,
            ("tenant_id", "asset_id", "source_id", "staff_source", "status"),
        )
    )
