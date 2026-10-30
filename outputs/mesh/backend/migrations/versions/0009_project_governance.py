"""Versioned project approval policies, immutable reviews and proposal snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade():
    op.add_column("projects", sa.Column("approval_policy", sa.JSON(), nullable=True))
    op.create_table(
        "project_approval_policies",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("required_senior_reviews", sa.Integer(), nullable=False),
        sa.Column("reviewers_must_be_members", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.UniqueConstraint("organization_id", "version"),
        sa.CheckConstraint("version > 0 AND required_senior_reviews BETWEEN 1 AND 5"),
    )
    op.create_index(
        "ix_project_approval_policies_organization_id",
        "project_approval_policies",
        ["organization_id"],
    )
    op.create_table(
        "project_reviews",
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("reviewer_id", sa.String(36), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reviewer_id"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        sa.UniqueConstraint("organization_id", "project_id", "reviewer_id"),
    )
    op.create_index("ix_project_reviews_organization_id", "project_reviews", ["organization_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("project_approval_policies", "project_reviews"):
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(f"""CREATE POLICY tenant_boundary ON "{table}"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
            op.execute(
                f"CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
            )
            for role in ("anon", "authenticated"):
                op.execute(f"""DO $mesh_project_grants$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                        REVOKE ALL ON TABLE public."{table}" FROM {role};
                    END IF;
                END; $mesh_project_grants$;""")


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
