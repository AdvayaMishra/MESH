"""Durable, tenant-bound billing collections and immutable terminal observations."""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"


def upgrade():
    op.create_table(
        "billing_collections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("requested_session_id", sa.String(36), nullable=True),
        sa.Column("requested_aal", sa.String(4), nullable=False),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("provider_account_id", sa.String(12), nullable=False),
        sa.Column("binding_revision", sa.String(64), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("dispatch_token", sa.String(36), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("report", sa.JSON(none_as_null=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["requested_by", "requested_session_id"],
            ["identity_sessions.user_id", "identity_sessions.provider_session_id"],
        ),
        sa.UniqueConstraint("organization_id", "request_key", name="uq_billing_collection_request"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','ambiguous','cancelled')",
            name="ck_billing_collection_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 1", name="ck_billing_collection_attempts"
        ),
        sa.CheckConstraint("requested_aal IN ('aal1','aal2')", name="ck_billing_collection_aal"),
        sa.CheckConstraint(
            "length(request_key)=36 AND length(binding_revision)=64 AND length(provider_account_id)=12 AND length(period)=7",
            name="ck_billing_collection_identity",
        ),
        sa.CheckConstraint(
            "(dispatch_token IS NULL) = (dispatched_at IS NULL)",
            name="ck_billing_collection_dispatch_pair",
        ),
        sa.CheckConstraint(
            "(attempts=0 AND dispatch_token IS NULL) OR (attempts=1 AND dispatch_token IS NOT NULL)",
            name="ck_billing_collection_dispatch_attempt",
        ),
        sa.CheckConstraint(
            "(status='queued' AND attempts=0 AND lease_until IS NULL AND finished_at IS NULL) OR (status='running' AND attempts=1 AND lease_until IS NOT NULL AND finished_at IS NULL) OR (status IN ('completed','failed','ambiguous','cancelled') AND lease_until IS NULL AND finished_at IS NOT NULL)",
            name="ck_billing_collection_lifecycle",
        ),
        sa.CheckConstraint(
            "(status='completed' AND report IS NOT NULL AND error_code IS NULL) OR (status!='completed' AND report IS NULL)",
            name="ck_billing_collection_result",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed','failed','ambiguous') OR attempts=1",
            name="ck_billing_collection_terminal_dispatch",
        ),
    )
    op.create_index(
        "ix_billing_collections_organization_id", "billing_collections", ["organization_id"]
    )
    op.create_index(
        "ix_billing_collection_queue",
        "billing_collections",
        ["organization_id", "status", "created_at"],
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "billing_collections" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "billing_collections" FORCE ROW LEVEL SECURITY')
    op.execute("""CREATE POLICY tenant_boundary ON "billing_collections"
        USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
        WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
    op.execute("""ALTER TABLE billing_collections ADD CONSTRAINT ck_billing_report_scope CHECK (
      report IS NULL OR (
        octet_length(report::text) <= 524288
        AND COALESCE(json_typeof(report)='object',false)
        AND COALESCE(report->>'organization_id'=organization_id,false)
        AND COALESCE(report->>'provider_account_id'=provider_account_id,false)
        AND COALESCE(report->>'period'=period,false)
        AND COALESCE(report->>'provider'='aws',false)
        AND COALESCE(report->>'partition'='aws',false)
        AND COALESCE(report->>'metric'='UnblendedCost',false)
        AND COALESCE(report->>'invoice_verified'='false',false)
        AND COALESCE(report->>'synthetic'=synthetic::text,false)
        AND COALESCE(report->>'provenance'=CASE WHEN synthetic THEN 'synthetic_fixture' ELSE 'authorized_provider' END,false)
      ))""")
    op.execute("""CREATE FUNCTION mesh_guard_billing_collection() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public AS $$
      BEGIN
        IF TG_OP='INSERT' THEN
          IF NEW.status!='queued' OR NEW.attempts!=0 THEN
            RAISE EXCEPTION 'Billing collections must start with undispatched admission';
          END IF;
          RETURN NEW;
        END IF;
        IF ROW(NEW.id,NEW.organization_id,NEW.created_at,NEW.requested_by,NEW.requested_session_id,NEW.requested_aal,NEW.request_key,NEW.period,NEW.provider_account_id,NEW.binding_revision,NEW.synthetic)
          IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.created_at,OLD.requested_by,OLD.requested_session_id,OLD.requested_aal,OLD.request_key,OLD.period,OLD.provider_account_id,OLD.binding_revision,OLD.synthetic)
        THEN RAISE EXCEPTION 'Billing admission is immutable'; END IF;
        IF OLD.status NOT IN ('queued','running') THEN
          RAISE EXCEPTION 'Billing terminal evidence is immutable';
        END IF;
        IF (OLD.status='queued' AND NEW.status NOT IN ('running','cancelled'))
          OR (OLD.status='running' AND NEW.status NOT IN ('completed','failed','ambiguous','cancelled'))
        THEN RAISE EXCEPTION 'Invalid billing lifecycle transition'; END IF;
        IF OLD.dispatch_token IS NOT NULL AND ROW(NEW.dispatch_token,NEW.dispatched_at,NEW.attempts)
          IS DISTINCT FROM ROW(OLD.dispatch_token,OLD.dispatched_at,OLD.attempts)
        THEN RAISE EXCEPTION 'Billing dispatch ownership is immutable'; END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER billing_collection_guard BEFORE INSERT OR UPDATE ON billing_collections FOR EACH ROW EXECUTE FUNCTION mesh_guard_billing_collection()"
    )
    op.execute(
        "CREATE TRIGGER no_billing_collection_delete BEFORE DELETE ON billing_collections FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
    )
    op.execute("REVOKE ALL ON TABLE billing_collections FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION mesh_guard_billing_collection() FROM PUBLIC")
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $billing_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
            REVOKE ALL ON TABLE billing_collections FROM {role};
            REVOKE ALL ON FUNCTION mesh_guard_billing_collection() FROM {role};
          END IF;
        END $billing_acl$""")
    op.execute("""DO $billing_runtime$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON TABLE billing_collections TO mesh_runtime;
        REVOKE DELETE ON TABLE billing_collections FROM mesh_runtime;
      END IF;
    END $billing_runtime$""")


def downgrade():
    raise RuntimeError("Billing evidence retirement requires a reviewed recovery migration")
