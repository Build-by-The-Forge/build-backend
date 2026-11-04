"""M3-D: ownership, classification, blobs, scans, rights, publication and quotas

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-05 09:00:00.000000

Implements docs/m3-d-migration-0030.md, approved at da57071 (#89), exactly.
No route behaviour changes. Every existing document becomes `unclassified`
through a default, and nothing else is backfilled or repaired.

The whole upgrade is one transaction. Its first statement looks for assets
with more than one active ingestion job; if there are any it raises, naming
every asset and job, and nothing has changed.

Downgrading restores uq_content_assets_tenant_hash, so it fails if the data
holds what only 0030 allows: two owners of the same bytes, or a deleted
document sharing a hash. That's refused loudly rather than repaired.
A downgrade also drops owner_user_id, so upgrading again over private sources
created under 0030 fails ck_content_sources_owner, again loudly.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

OWNERSHIP = "('institutional', 'personal', 'unclassified')"

APPEND_ONLY = """
CREATE OR REPLACE FUNCTION content_refuse_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- A cascade from a tenant or a document runs inside the referential
    -- action, one trigger level deeper; anything else is refused.
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$;
"""

PUBLICATION_RULES = """
CREATE OR REPLACE FUNCTION content_publication_rules() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF pg_trigger_depth() > 1 THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'content_publications rows are never deleted'
            USING ERRCODE = 'restrict_violation';
    END IF;
    -- The consent never changes.
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
        OR NEW.declaration_id IS DISTINCT FROM OLD.declaration_id
        OR NEW.requested_by IS DISTINCT FROM OLD.requested_by
        OR NEW.consent_version IS DISTINCT FROM OLD.consent_version
        OR NEW.requested_at IS DISTINCT FROM OLD.requested_at THEN
        RAISE EXCEPTION 'a publication''s consent can''t change'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
        (OLD.state = 'requested' AND NEW.state IN ('published', 'closed', 'withdrawn'))
        OR (OLD.state = 'published' AND NEW.state IN ('withdrawn', 'taken_down'))
    ) THEN
        RAISE EXCEPTION 'publication can''t move from % to %', OLD.state, NEW.state
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;
"""


def _refuse_active_job_conflicts() -> None:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT asset_id, string_agg(id, ', ' ORDER BY id) AS jobs"
                " FROM content_ingestion_jobs WHERE status NOT IN ('ready', 'failed')"
                " GROUP BY asset_id HAVING count(*) > 1 ORDER BY asset_id"
            )
        )
        .all()
    )
    if rows:
        listed = "; ".join(f"asset {row.asset_id}: jobs {row.jobs}" for row in rows)
        raise RuntimeError(
            "migration 0030 stopped: these assets have more than one active ingestion job, and"
            " choosing which to fail is an operator's decision (scripts/report_active_job_conflicts.py)."
            f" Nothing was changed. {listed}"
        )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    _refuse_active_job_conflicts()

    # 0. Keys for tenant-consistent references.
    op.create_unique_constraint("uq_courses_tenant_id_id", "courses", ["tenant_id", "id"])
    op.create_unique_constraint("uq_content_assets_tenant_id_id", "content_assets", ["tenant_id", "id"])

    # 4. Blobs, before the column that references them.
    op.create_table(
        "content_blobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_sha256", sa.CHAR(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("generation", sa.String(36), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "id", name="uq_content_blobs_tenant_id_id"),
        sa.UniqueConstraint("object_key", name="uq_content_blobs_object_key"),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_content_blobs_sha256"),
        sa.CheckConstraint("size_bytes > 0", name="ck_content_blobs_size"),
        sa.CheckConstraint("state IN ('pending', 'active', 'deleting')", name="ck_content_blobs_state"),
        sa.CheckConstraint("state <> 'pending' OR claimed_until IS NOT NULL", name="ck_content_blobs_pending_claim"),
        sa.CheckConstraint("state <> 'active' OR claimed_until IS NULL", name="ck_content_blobs_active_claim"),
    )
    op.create_index(
        "ux_content_blobs_live_hash",
        "content_blobs",
        ["tenant_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("state <> 'deleting'"),
    )
    op.create_index("ix_content_blobs_sweep", "content_blobs", ["state", "claimed_until"])

    # 1. Documents.
    op.add_column(
        "content_assets",
        sa.Column("ownership_class", sa.String(20), nullable=False, server_default="unclassified"),
    )
    op.add_column(
        "content_assets",
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column("content_assets", sa.Column("blob_id", sa.String(36), nullable=True))
    op.add_column("content_assets", sa.Column("trust_class", sa.String(20), nullable=True))
    op.add_column("content_assets", sa.Column("course_id", sa.String(36), nullable=True))
    op.add_column("content_assets", sa.Column("level", sa.SmallInteger(), nullable=True))
    op.add_column("content_assets", sa.Column("semester", sa.SmallInteger(), nullable=True))
    op.add_column("content_assets", sa.Column("document_type", sa.String(30), nullable=True))
    op.create_foreign_key(
        "fk_content_assets_blob",
        "content_assets",
        "content_blobs",
        ["tenant_id", "blob_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    # SET NULL with a column list (PostgreSQL 15+): the tenant stays.
    op.execute(
        "ALTER TABLE content_assets ADD CONSTRAINT fk_content_assets_course"
        " FOREIGN KEY (tenant_id, course_id) REFERENCES courses (tenant_id, id)"
        " ON DELETE SET NULL (course_id)"
    )
    for name, condition in (
        ("ck_content_assets_ownership_class", f"ownership_class IN {OWNERSHIP}"),
        ("ck_content_assets_owner", "(ownership_class = 'personal') = (owner_user_id IS NOT NULL)"),
        ("ck_content_assets_blob_tenant", "blob_id IS NULL OR tenant_id IS NOT NULL"),
        ("ck_content_assets_course_tenant", "course_id IS NULL OR tenant_id IS NOT NULL"),
        ("ck_content_assets_trust_class", "trust_class IS NULL OR trust_class IN ('user_provided', 'staff_provided')"),
        ("ck_content_assets_level", "level IS NULL OR level IN (100, 200, 300, 400, 500, 600)"),
        ("ck_content_assets_semester", "semester IS NULL OR semester BETWEEN 1 AND 3"),
        (
            "ck_content_assets_document_type",
            "document_type IS NULL OR document_type IN"
            " ('lecture_notes', 'summary', 'assignment', 'project_report', 'slides', 'other')",
        ),
    ):
        op.create_check_constraint(name, "content_assets", condition)
    # The two partial indexes replace the tenant-wide one in this transaction,
    # so there's no moment without the rule.
    op.create_index(
        "ux_content_assets_shared_hash",
        "content_assets",
        ["tenant_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("ownership_class <> 'personal' AND status <> 'deleted'"),
    )
    op.create_index(
        "ux_content_assets_personal_hash",
        "content_assets",
        ["tenant_id", "owner_user_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("ownership_class = 'personal' AND status <> 'deleted'"),
    )
    op.drop_constraint("uq_content_assets_tenant_hash", "content_assets", type_="unique")
    op.create_index(
        "ix_content_assets_owner",
        "content_assets",
        ["tenant_id", "owner_user_id"],
        postgresql_where=sa.text("owner_user_id IS NOT NULL"),
    )

    # 2. Sources.
    op.add_column(
        "content_sources",
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_check_constraint(
        "ck_content_sources_owner", "content_sources", "(visibility = 'private') = (owner_user_id IS NOT NULL)"
    )
    op.create_index(
        "ux_content_sources_personal",
        "content_sources",
        ["tenant_id", "owner_user_id"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NOT NULL"),
    )

    # 3. Classification decisions, append-only.
    op.create_table(
        "content_ownership_classifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("previous_class", sa.String(20), nullable=False),
        sa.Column("new_class", sa.String(20), nullable=False),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decided_via", sa.String(20), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_content_classifications_asset",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"previous_class IN {OWNERSHIP}", name="ck_content_classifications_previous"),
        sa.CheckConstraint(f"new_class IN {OWNERSHIP}", name="ck_content_classifications_new"),
        sa.CheckConstraint("new_class <> previous_class", name="ck_content_classifications_change"),
        sa.CheckConstraint("decided_via IN ('operator_command', 'staff_route')", name="ck_content_classifications_via"),
        sa.CheckConstraint("length(trim(evidence_reference)) > 0", name="ck_content_classifications_evidence"),
        sa.CheckConstraint("decided_via <> 'operator_command' OR run_id IS NOT NULL", name="ck_content_classifications_run"),
    )
    op.create_index(
        "ix_content_classifications_asset",
        "content_ownership_classifications",
        ["tenant_id", "asset_id", sa.text("decided_at DESC")],
    )

    # 5. Scans.
    op.create_table(
        "content_scans",
        sa.Column("asset_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("verdict", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("fence", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scanner", sa.String(100), nullable=True),
        sa.Column("signature_version", sa.String(100), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_content_scans_asset",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("verdict IN ('pending', 'accepted', 'rejected')", name="ck_content_scans_verdict"),
        sa.CheckConstraint("fence >= 0", name="ck_content_scans_fence"),
        sa.CheckConstraint("attempts >= 0", name="ck_content_scans_attempts"),
        sa.CheckConstraint(
            "verdict = 'pending' OR (scanner IS NOT NULL AND signature_version IS NOT NULL AND scanned_at IS NOT NULL)",
            name="ck_content_scans_recorded",
        ),
    )
    op.create_index("ix_content_scans_due", "content_scans", ["next_attempt_at"], postgresql_where=sa.text("verdict = 'pending'"))
    op.create_index(
        "ix_content_scans_rescan",
        "content_scans",
        ["signature_version"],
        postgresql_where=sa.text("verdict = 'accepted'"),
    )

    # 6. Rights assertions, append-only.
    op.create_table(
        "content_rights_assertions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("asserted_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("rights_basis", sa.String(30), nullable=False),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("redistribution", sa.String(20), nullable=False),
        sa.Column("ai_use", sa.String(20), nullable=False, server_default="not_permitted"),
        sa.Column("declaration_version", sa.String(64), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("asserted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_content_rights_asset",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "asset_id", "id", name="uq_content_rights_tenant_asset_id"),
        sa.CheckConstraint(
            "kind IN ('owner_declaration', 'staff_review', 'copied_source_default')", name="ck_content_rights_kind"
        ),
        sa.CheckConstraint(
            "rights_basis IN ('own_work', 'lecturer_provided', 'institution_licensed', 'publisher_licensed',"
            " 'public_domain', 'unknown')",
            name="ck_content_rights_basis",
        ),
        sa.CheckConstraint(
            "audience IN ('owner', 'tenant', 'faculty', 'department', 'programme', 'course')",
            name="ck_content_rights_audience",
        ),
        sa.CheckConstraint("redistribution IN ('none', 'tenant_only', 'permitted')", name="ck_content_rights_redistribution"),
        sa.CheckConstraint("ai_use IN ('not_permitted', 'permitted')", name="ck_content_rights_ai_use"),
        sa.CheckConstraint(
            "kind <> 'owner_declaration' OR (declaration_version IS NOT NULL AND length(trim(declaration_version)) > 0)",
            name="ck_content_rights_declaration_version",
        ),
        sa.CheckConstraint(
            "kind <> 'staff_review' OR (outcome IS NOT NULL AND outcome IN ('accepted', 'rejected')"
            " AND reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_content_rights_review",
        ),
        sa.CheckConstraint("kind = 'staff_review' OR outcome IS NULL", name="ck_content_rights_outcome_only_review"),
    )
    op.create_index(
        "ix_content_rights_asset",
        "content_rights_assertions",
        ["tenant_id", "asset_id", sa.text("asserted_at DESC")],
    )

    # 7. Publication consent.
    op.create_table(
        "content_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("declaration_id", sa.String(36), nullable=False),
        sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consent_version", sa.String(64), nullable=False),
        sa.Column("state", sa.String(12), nullable=False, server_default="requested"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_content_publications_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id", "declaration_id"],
            [
                "content_rights_assertions.tenant_id",
                "content_rights_assertions.asset_id",
                "content_rights_assertions.id",
            ],
            name="fk_content_publications_declaration",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(trim(consent_version)) > 0", name="ck_content_publications_consent"),
        sa.CheckConstraint(
            "state IN ('requested', 'published', 'withdrawn', 'taken_down', 'closed')",
            name="ck_content_publications_state",
        ),
        sa.CheckConstraint(
            "state NOT IN ('published', 'taken_down') OR published_at IS NOT NULL",
            name="ck_content_publications_published_at",
        ),
        sa.CheckConstraint(
            "state NOT IN ('requested', 'closed') OR published_at IS NULL",
            name="ck_content_publications_never_published",
        ),
        sa.CheckConstraint("hidden_at IS NULL OR state = 'published'", name="ck_content_publications_hidden"),
        sa.CheckConstraint("(state IN ('requested', 'published')) = (ended_at IS NULL)", name="ck_content_publications_ended"),
        sa.CheckConstraint(
            "ended_at IS NULL OR state = 'closed' OR ended_by IS NOT NULL", name="ck_content_publications_ended_by"
        ),
        sa.CheckConstraint(
            "state <> 'taken_down' OR (end_reason IS NOT NULL AND length(trim(end_reason)) > 0)",
            name="ck_content_publications_takedown_reason",
        ),
    )
    op.create_index(
        "ux_content_publications_live",
        "content_publications",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('requested', 'published')"),
    )

    # 8. Quotas.
    op.create_table(
        "content_upload_usage",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("usage_day", sa.Date(), nullable=False),
        sa.Column("uploads_on_day", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("stored_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("uploads_on_day >= 0", name="ck_content_upload_usage_uploads"),
        sa.CheckConstraint("stored_bytes >= 0", name="ck_content_upload_usage_bytes"),
    )
    op.create_table(
        "content_retry_usage",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("asset_id", sa.String(36), primary_key=True),
        sa.Column("usage_day", sa.Date(), primary_key=True),
        sa.Column("retries", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["content_assets.tenant_id", "content_assets.id"],
            name="fk_content_retry_usage_asset",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("retries >= 0", name="ck_content_retry_usage_retries"),
    )

    # 9. One active job per asset. The check above ran first.
    op.create_index(
        "ux_content_ingestion_jobs_active_asset",
        "content_ingestion_jobs",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('ready', 'failed')"),
    )

    # Append-only and publication rules.
    op.execute(APPEND_ONLY)
    for table in ("content_ownership_classifications", "content_rights_assertions"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION content_refuse_change()"
        )
    op.execute(PUBLICATION_RULES)
    op.execute(
        "CREATE TRIGGER content_publications_rules BEFORE UPDATE OR DELETE ON content_publications"
        " FOR EACH ROW EXECUTE FUNCTION content_publication_rules()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS content_publications_rules ON content_publications")
    op.execute("DROP TRIGGER IF EXISTS content_rights_assertions_append_only ON content_rights_assertions")
    op.execute("DROP TRIGGER IF EXISTS content_ownership_classifications_append_only ON content_ownership_classifications")
    op.execute("DROP FUNCTION IF EXISTS content_publication_rules()")
    op.execute("DROP FUNCTION IF EXISTS content_refuse_change()")
    op.drop_index("ux_content_ingestion_jobs_active_asset", table_name="content_ingestion_jobs")
    op.drop_table("content_retry_usage")
    op.drop_table("content_upload_usage")
    op.drop_table("content_publications")
    op.drop_table("content_rights_assertions")
    op.drop_table("content_scans")
    op.drop_table("content_ownership_classifications")
    op.drop_index("ux_content_sources_personal", table_name="content_sources")
    op.drop_constraint("ck_content_sources_owner", "content_sources", type_="check")
    op.drop_column("content_sources", "owner_user_id")
    op.drop_index("ix_content_assets_owner", table_name="content_assets")
    op.create_unique_constraint("uq_content_assets_tenant_hash", "content_assets", ["tenant_id", "content_sha256"])
    op.drop_index("ux_content_assets_personal_hash", table_name="content_assets")
    op.drop_index("ux_content_assets_shared_hash", table_name="content_assets")
    for name in (
        "ck_content_assets_document_type",
        "ck_content_assets_semester",
        "ck_content_assets_level",
        "ck_content_assets_trust_class",
        "ck_content_assets_course_tenant",
        "ck_content_assets_blob_tenant",
        "ck_content_assets_owner",
        "ck_content_assets_ownership_class",
    ):
        op.drop_constraint(name, "content_assets", type_="check")
    op.drop_constraint("fk_content_assets_course", "content_assets", type_="foreignkey")
    op.drop_constraint("fk_content_assets_blob", "content_assets", type_="foreignkey")
    for column in (
        "document_type",
        "semester",
        "level",
        "course_id",
        "trust_class",
        "blob_id",
        "owner_user_id",
        "ownership_class",
    ):
        op.drop_column("content_assets", column)
    op.drop_index("ix_content_blobs_sweep", table_name="content_blobs")
    op.drop_index("ux_content_blobs_live_hash", table_name="content_blobs")
    op.drop_table("content_blobs")
    op.drop_constraint("uq_content_assets_tenant_id_id", "content_assets", type_="unique")
    op.drop_constraint("uq_courses_tenant_id_id", "courses", type_="unique")
