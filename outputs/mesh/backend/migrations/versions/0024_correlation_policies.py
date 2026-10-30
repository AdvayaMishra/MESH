"""Versioned immutable correlation policies and retained incident provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade():
    op.create_table(
        "correlation_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "version"),
        sa.CheckConstraint("version > 0", name="ck_correlation_policy_version"),
    )
    op.create_index(
        "ix_correlation_policies_organization_id", "correlation_policies", ["organization_id"]
    )
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("correlation_policy_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("correlation_snapshot", sa.JSON(), nullable=True))
        batch.create_foreign_key(
            "fk_incident_correlation_policy",
            "correlation_policies",
            ["organization_id", "correlation_policy_id"],
            ["organization_id", "id"],
        )
        batch.create_check_constraint(
            "ck_incident_correlation_snapshot",
            "correlation_policy_id IS NULL OR correlation_snapshot IS NOT NULL",
        )
        batch.create_index(
            "ix_incident_org_correlation_policy", ["organization_id", "correlation_policy_id"]
        )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "correlation_policies" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "correlation_policies" FORCE ROW LEVEL SECURITY')
        op.execute("""CREATE POLICY tenant_boundary ON "correlation_policies"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
        op.execute(
            "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON correlation_policies FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        op.execute(
            "CREATE TRIGGER correlation_snapshot_immutable BEFORE UPDATE OF correlation_policy_id,correlation_snapshot ON incidents FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        op.execute("REVOKE ALL ON TABLE correlation_policies FROM PUBLIC")
        for role in ("anon", "authenticated", "service_role"):
            op.execute(f"""DO $correlation_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    REVOKE ALL ON TABLE correlation_policies FROM {role};
                END IF;
            END $correlation_acl$;""")
        op.execute("""DO $correlation_runtime$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                GRANT SELECT,INSERT ON TABLE correlation_policies TO mesh_runtime;
                REVOKE UPDATE,DELETE ON TABLE correlation_policies FROM mesh_runtime;
            END IF;
        END $correlation_runtime$;""")


def downgrade():
    raise RuntimeError("Correlation history retirement requires a reviewed recovery migration")
