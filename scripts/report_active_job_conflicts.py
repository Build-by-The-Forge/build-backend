"""Documents with more than one active ingestion job (read-only).

    python -m scripts.report_active_job_conflicts

Migration 0030 runs the same query first and stops, changing nothing, if it
finds any: choosing which job to fail is the operator's decision. Run this
before migrating. Exit code 0 means the migration won't stop on this.
"""

from __future__ import annotations

import sys

from scripts._read_only_report import report

SQL = (
    "SELECT tenant_id, asset_id, string_agg(id || ' (' || status || ')', ', ' ORDER BY id) AS jobs"
    " FROM content_ingestion_jobs WHERE status NOT IN ('ready', 'failed')"
    " GROUP BY tenant_id, asset_id HAVING count(*) > 1 ORDER BY tenant_id, asset_id"
)

if __name__ == "__main__":
    sys.exit(report("documents with more than one active job", SQL, ("tenant_id", "asset_id", "active jobs")))
