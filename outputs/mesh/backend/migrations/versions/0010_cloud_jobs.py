"""Durable tenant-bound cloud assessment jobs and report references."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade():
    op.create_index(
        "uq_cloud_assessments_org_id", "cloud_assessments", ["organization_id", "id"], unique=True
    )
    op.create_table(
        "cloud_assessment_jobs",
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessment_id", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["cloud_assessments.organization_id", "cloud_assessments.id"],
        ),
        sa.UniqueConstraint("organization_id", "request_key"),
        sa.CheckConstraint("status IN ('queued','running','completed','dead_letter','cancelled')"),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 3"),
    )
    op.create_index(
        "ix_cloud_assessment_jobs_organization_id", "cloud_assessment_jobs", ["organization_id"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "cloud_assessment_jobs" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "cloud_assessment_jobs" FORCE ROW LEVEL SECURITY')
        op.execute("""CREATE POLICY tenant_boundary ON "cloud_assessment_jobs"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $mesh_cloud_job_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    REVOKE ALL ON TABLE public.cloud_assessment_jobs FROM {role};
                END IF;
            END; $mesh_cloud_job_grants$;""")


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
