"""Immutable tenant-bound signed webhook delivery receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade():
    op.create_table(
        "webhook_deliveries",
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("delivery_id", sa.String(36), nullable=False),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.UniqueConstraint("organization_id", "provider", "delivery_id"),
        sa.UniqueConstraint("organization_id", "provider", "payload_digest"),
    )
    op.create_index(
        "ix_webhook_deliveries_organization_id", "webhook_deliveries", ["organization_id"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "webhook_deliveries" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "webhook_deliveries" FORCE ROW LEVEL SECURITY')
        op.execute("""CREATE POLICY tenant_boundary ON "webhook_deliveries"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
        op.execute(
            "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON webhook_deliveries FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $mesh_webhook_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    REVOKE ALL ON TABLE public.webhook_deliveries FROM {role};
                END IF;
            END; $mesh_webhook_grants$;""")


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
