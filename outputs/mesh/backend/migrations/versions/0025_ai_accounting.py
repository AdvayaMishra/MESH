"""Durable AI dispatch intent, immutable observations and scoped usage receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade():
    op.create_table(
        "ai_requests",
        sa.Column("requested_by", sa.String(36), nullable=False, primary_key=False),
        sa.Column("purpose", sa.String(30), nullable=False, primary_key=False),
        sa.Column("provider", sa.String(50), nullable=False, primary_key=False),
        sa.Column("model", sa.String(100), nullable=False, primary_key=False),
        sa.Column("status", sa.String(30), nullable=False, primary_key=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False, primary_key=False),
        sa.Column("context_digest", sa.String(64), nullable=False, primary_key=False),
        sa.Column("endpoint_digest", sa.String(64), nullable=False, primary_key=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("reserved_input_units", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("reserved_output_units", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("reserved_cost", sa.Numeric(14, 6), nullable=True, primary_key=False),
        sa.Column("currency", sa.String(3), nullable=True, primary_key=False),
        sa.Column("dispatch_token", sa.String(36), nullable=True, primary_key=False),
        sa.Column(
            "dispatch_deadline", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column("observed_input_units", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("observed_output_units", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("observed_cost", sa.Numeric(14, 6), nullable=True, primary_key=False),
        sa.Column("observed_currency", sa.String(3), nullable=True, primary_key=False),
        sa.Column("reconciliation_digest", sa.String(64), nullable=True, primary_key=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "status != 'cancelled' OR dispatch_token IS NULL", name="ck_ai_request_cancelled_unsent"
        ),
        sa.CheckConstraint(
            "(reserved_cost IS NULL) = (currency IS NULL) AND (observed_cost IS NULL) = (observed_currency IS NULL)",
            name="ck_ai_request_currency_pairs",
        ),
        sa.CheckConstraint(
            "length(context_digest)=64 AND length(endpoint_digest)=64", name="ck_ai_request_digests"
        ),
        sa.CheckConstraint(
            "status NOT IN ('dispatched','succeeded','ambiguous','reconciled_charge','reconciled_no_charge') OR (dispatch_token IS NOT NULL AND dispatched_at IS NOT NULL)",
            name="ck_ai_request_dispatch_marker",
        ),
        sa.CheckConstraint(
            "(dispatch_token IS NULL) = (dispatched_at IS NULL)", name="ck_ai_request_dispatch_pair"
        ),
        sa.CheckConstraint(
            "status NOT IN ('reserved','dispatched') OR (observed_input_units IS NULL AND observed_output_units IS NULL AND observed_cost IS NULL AND observed_currency IS NULL)",
            name="ck_ai_request_no_early_observation",
        ),
        sa.CheckConstraint(
            "observed_cost IS NULL OR observed_cost >= 0", name="ck_ai_request_observed_cost"
        ),
        sa.CheckConstraint(
            "observed_input_units IS NULL OR observed_input_units >= 0",
            name="ck_ai_request_observed_input",
        ),
        sa.CheckConstraint(
            "observed_output_units IS NULL OR observed_output_units >= 0",
            name="ck_ai_request_observed_output",
        ),
        sa.CheckConstraint(
            "status NOT IN ('succeeded','reconciled_charge') OR (observed_input_units IS NOT NULL AND observed_output_units IS NOT NULL)",
            name="ck_ai_request_observed_units",
        ),
        sa.CheckConstraint(
            "status != 'reconciled_charge' OR (observed_cost IS NOT NULL AND observed_currency IS NOT NULL)",
            name="ck_ai_request_reconciled_charge",
        ),
        sa.CheckConstraint(
            "(status IN ('reconciled_charge','reconciled_no_charge')) = (reconciliation_digest IS NOT NULL)",
            name="ck_ai_request_reconciliation_state",
        ),
        sa.CheckConstraint(
            "reserved_cost IS NULL OR reserved_cost >= 0", name="ck_ai_request_reserve_cost"
        ),
        sa.CheckConstraint(
            "reserved_input_units >= 0 AND reserved_output_units >= 0",
            name="ck_ai_request_reserve_units",
        ),
        sa.CheckConstraint(
            "((status IN ('reserved','dispatched','ambiguous')) AND settled_at IS NULL) OR ((status NOT IN ('reserved','dispatched','ambiguous')) AND settled_at IS NOT NULL)",
            name="ck_ai_request_settlement_state",
        ),
        sa.CheckConstraint(
            "status IN ('reserved','dispatched','succeeded','ambiguous','not_dispatched','cancelled','reconciled_charge','reconciled_no_charge')",
            name="ck_ai_request_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint(
            "organization_id", "id", "period_start", name="uq_ai_request_admission_period"
        ),
    )
    op.create_index(
        "ix_ai_request_org_period_status",
        "ai_requests",
        ["organization_id", "period_start", "status"],
    )
    op.create_index("ix_ai_requests_organization_id", "ai_requests", ["organization_id"])
    op.create_table(
        "ai_request_events",
        sa.Column("request_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("position", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("actor_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("kind", sa.String(40), nullable=False, primary_key=False),
        sa.Column("details", sa.JSON(), nullable=False, primary_key=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("position > 0", name="ck_ai_request_event_position"),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"], ["ai_requests.organization_id", "ai_requests.id"]
        ),
        sa.UniqueConstraint("organization_id", "request_id", "position"),
    )
    op.create_index(
        "ix_ai_request_event_scope", "ai_request_events", ["organization_id", "request_id"]
    )
    op.create_index(
        "ix_ai_request_events_organization_id", "ai_request_events", ["organization_id"]
    )
    with op.batch_alter_table("ai_usage") as batch:
        batch.add_column(sa.Column("request_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("admission_period_start", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_ai_usage_request_period",
            "ai_requests",
            ["organization_id", "request_id", "admission_period_start"],
            ["organization_id", "id", "period_start"],
        )
        batch.create_unique_constraint("uq_ai_usage_request", ["organization_id", "request_id"])
        batch.create_check_constraint(
            "ck_ai_usage_request_period_pair",
            "(request_id IS NULL) = (admission_period_start IS NULL)",
        )
    if op.get_bind().dialect.name == "postgresql":
        for table in ("ai_requests", "ai_request_events"):
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(f"""CREATE POLICY tenant_boundary ON "{table}"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
            op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(
            "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON ai_request_events FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        op.execute(
            "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON ai_usage FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        op.execute(
            "CREATE TRIGGER no_ai_request_delete BEFORE DELETE ON ai_requests FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        op.execute("""CREATE FUNCTION public.mesh_guard_ai_request() RETURNS trigger
        LANGUAGE plpgsql SET search_path='' AS $guard$
        BEGIN
            IF ROW(NEW.id,NEW.organization_id,NEW.created_at,NEW.requested_by,NEW.purpose,NEW.provider,NEW.model,NEW.policy_snapshot::jsonb,NEW.context_digest,NEW.endpoint_digest,NEW.period_start,NEW.reserved_input_units,NEW.reserved_output_units,NEW.reserved_cost,NEW.currency)
                IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.created_at,OLD.requested_by,OLD.purpose,OLD.provider,OLD.model,OLD.policy_snapshot::jsonb,OLD.context_digest,OLD.endpoint_digest,OLD.period_start,OLD.reserved_input_units,OLD.reserved_output_units,OLD.reserved_cost,OLD.currency)
            THEN RAISE EXCEPTION 'AI request intent is immutable'; END IF;
            IF OLD.status IN ('succeeded','not_dispatched','cancelled') THEN
                RAISE EXCEPTION 'AI request terminal observation is immutable';
            END IF;
            IF OLD.status IN ('reconciled_charge','reconciled_no_charge') AND NEW.status=OLD.status THEN
                RAISE EXCEPTION 'AI reconciliation observation is immutable';
            END IF;
            IF OLD.dispatch_token IS NOT NULL AND ROW(NEW.dispatch_token,NEW.dispatched_at) IS DISTINCT FROM ROW(OLD.dispatch_token,OLD.dispatched_at)
            THEN RAISE EXCEPTION 'AI dispatch ownership is immutable'; END IF;
            IF OLD.dispatch_token IS NULL AND ROW(NEW.dispatch_token,NEW.dispatched_at) IS DISTINCT FROM ROW(OLD.dispatch_token,OLD.dispatched_at)
                AND NOT (OLD.status='reserved' AND NEW.status='dispatched')
            THEN RAISE EXCEPTION 'Invalid first dispatch marker'; END IF;
            IF NEW.dispatch_deadline IS DISTINCT FROM OLD.dispatch_deadline AND NOT (OLD.status='reserved' AND NEW.status='dispatched')
            THEN RAISE EXCEPTION 'AI dispatch deadline is immutable'; END IF;
            IF NEW.status<>OLD.status AND NOT (
                (OLD.status='reserved' AND NEW.status IN ('dispatched','not_dispatched','cancelled')) OR
                (OLD.status='dispatched' AND NEW.status IN ('succeeded','ambiguous','not_dispatched','reconciled_charge','reconciled_no_charge')) OR
                (OLD.status='ambiguous' AND NEW.status IN ('reconciled_charge','reconciled_no_charge')) OR
                (OLD.status IN ('reconciled_charge','reconciled_no_charge') AND NEW.status='ambiguous'))
            THEN RAISE EXCEPTION 'Invalid AI request state transition'; END IF;
            RETURN NEW;
        END $guard$""")
        op.execute(
            "CREATE TRIGGER ai_request_guard BEFORE UPDATE ON ai_requests FOR EACH ROW EXECUTE FUNCTION public.mesh_guard_ai_request()"
        )
        op.execute("REVOKE ALL ON FUNCTION public.mesh_guard_ai_request() FROM PUBLIC")
        for role in ("anon", "authenticated", "service_role"):
            op.execute(f"""DO $ai_acl$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                REVOKE ALL ON TABLE ai_requests,ai_request_events FROM {role};
                REVOKE ALL ON FUNCTION public.mesh_guard_ai_request() FROM {role};
            END IF; END $ai_acl$;""")
        op.execute("""DO $ai_runtime$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
            GRANT SELECT,INSERT,UPDATE ON TABLE ai_requests TO mesh_runtime;
            GRANT SELECT,INSERT ON TABLE ai_request_events TO mesh_runtime;
            REVOKE DELETE ON TABLE ai_requests FROM mesh_runtime;
            REVOKE UPDATE,DELETE ON TABLE ai_usage,ai_request_events FROM mesh_runtime;
        END IF; END $ai_runtime$;""")


def downgrade():
    raise RuntimeError("AI accounting history requires a reviewed recovery migration")
