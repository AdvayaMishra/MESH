"""Retain exact scan commit and dependency metadata without inventing historical provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade():
    with op.batch_alter_table("scan_jobs") as batch:
        batch.create_unique_constraint(
            "uq_scan_finding_provenance", ["organization_id", "repository_id", "id", "commit_sha"]
        )
    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("column", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("dependency", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("scan_job_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("commit_sha", sa.String(40), nullable=True))
        batch.create_foreign_key(
            "fk_finding_scan_commit",
            "scan_jobs",
            ["organization_id", "repository_id", "scan_job_id", "commit_sha"],
            ["organization_id", "repository_id", "id", "commit_sha"],
        )
        batch.create_check_constraint(
            "ck_finding_provenance_pair",
            "(scan_job_id IS NULL AND commit_sha IS NULL) OR (scan_job_id IS NOT NULL AND commit_sha IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_finding_commit_length", "commit_sha IS NULL OR length(commit_sha)=40"
        )
        batch.create_check_constraint(
            "ck_finding_column_positive", '"column" IS NULL OR "column">0'
        )
        batch.create_index(
            "ix_finding_org_repository_scan", ["organization_id", "repository_id", "scan_job_id"]
        )


def downgrade():
    raise RuntimeError("Retiring scan provenance requires a reviewed recovery migration")
