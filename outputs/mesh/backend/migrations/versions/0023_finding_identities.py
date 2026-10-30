"""Immutable, tenant/repository-scoped exact finding identities."""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade():
    op.create_table(
        "finding_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("repository_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("match_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "repository_id"],
            ["repositories.organization_id", "repositories.id"],
        ),
        sa.UniqueConstraint(
            "organization_id",
            "repository_id",
            "fingerprint",
            name="uq_finding_identity_fingerprint",
        ),
        sa.UniqueConstraint(
            "organization_id", "repository_id", "id", name="uq_finding_identity_scope"
        ),
        sa.CheckConstraint("length(fingerprint)=64", name="ck_finding_identity_fingerprint_length"),
    )
    op.create_index(
        "ix_finding_identities_organization_id", "finding_identities", ["organization_id"]
    )
    op.create_index(
        "ix_finding_identity_org_repository",
        "finding_identities",
        ["organization_id", "repository_id"],
    )
    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("identity_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_finding_identity_scope",
            "finding_identities",
            ["organization_id", "repository_id", "identity_id"],
            ["organization_id", "repository_id", "id"],
        )
        batch.create_index(
            "ix_finding_org_repository_identity",
            ["organization_id", "repository_id", "identity_id"],
        )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "finding_identities" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "finding_identities" FORCE ROW LEVEL SECURITY')
        op.execute("""CREATE POLICY tenant_boundary ON "finding_identities"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
        op.execute(
            "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON finding_identities FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        op.execute("REVOKE ALL ON TABLE finding_identities FROM PUBLIC")
        for role in ("anon", "authenticated", "service_role"):
            op.execute(f"""DO $identity_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    REVOKE ALL ON TABLE finding_identities FROM {role};
                END IF;
            END $identity_acl$;""")
        op.execute("""DO $identity_runtime$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                GRANT SELECT,INSERT ON TABLE finding_identities TO mesh_runtime;
                REVOKE UPDATE,DELETE ON TABLE finding_identities FROM mesh_runtime;
            END IF;
        END $identity_runtime$;""")


def downgrade():
    raise RuntimeError("Identity history retirement requires a reviewed recovery migration")
