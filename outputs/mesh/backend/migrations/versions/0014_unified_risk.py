"""Immutable tenant-scoped risk policies and assessment snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade():
    op.create_index(
        "ix_event_org_time_id", "security_events", ["organization_id", "occurred_at", "id"]
    )
    op.create_table(
        "risk_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "version"),
        sa.CheckConstraint("version > 0"),
    )
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "policy_id"], ["risk_policies.organization_id", "risk_policies.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        sa.UniqueConstraint("organization_id", "request_key"),
        sa.CheckConstraint("window_start <= window_end"),
    )
    op.create_index(
        "ix_risk_assessment_window",
        "risk_assessments",
        ["organization_id", "synthetic", "window_end", "window_start"],
    )
    for table in ("risk_policies", "risk_assessments"):
        op.create_index("ix_" + table + "_organization_id", table, ["organization_id"])
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f'REVOKE ALL ON TABLE public."{table}" FROM PUBLIC')
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(f"""CREATE POLICY tenant_boundary ON "{table}"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
            op.execute(
                f"CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
            )
            for role in ("anon", "authenticated"):
                op.execute(f"""DO $mesh_risk$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                        REVOKE ALL ON TABLE public."{table}" FROM {role};
                    END IF;
                END; $mesh_risk$;""")
            op.execute(f"""DO $mesh_risk_runtime$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                    GRANT SELECT, INSERT ON TABLE public."{table}" TO mesh_runtime;
                    REVOKE UPDATE, DELETE ON TABLE public."{table}" FROM mesh_runtime;
                END IF;
            END; $mesh_risk_runtime$;""")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE OR REPLACE FUNCTION public.mesh_retire_telemetry(retention_days integer, batch_size integer)
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog
        AS $mesh_retention$
        DECLARE
            scoped_org text := nullif(current_setting('mesh.organization_id', true), '');
            candidates text[];
            removed integer := 0;
        BEGIN
            IF scoped_org IS NULL OR retention_days IS NULL OR batch_size IS NULL
                OR retention_days < 30 OR retention_days > 3650 OR batch_size < 1 OR batch_size > 1000 THEN
                RAISE EXCEPTION 'Explicit tenant and bounded retention policy required';
            END IF;
            PERFORM id FROM public.organizations WHERE id=scoped_org FOR NO KEY UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Retention tenant not found'; END IF;
            SELECT array_agg(selected.id) INTO candidates FROM (
                SELECT e.id FROM public.security_events e
                WHERE e.organization_id=scoped_org
                    AND e.occurred_at < now() - make_interval(days => retention_days)
                    AND NOT EXISTS (
                        SELECT 1 FROM public.incident_events link
                        WHERE link.organization_id=scoped_org AND link.event_id=e.id
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM public.incidents i
                        WHERE i.organization_id=scoped_org AND i.event_ids::jsonb ? e.id
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM public.risk_assessments r
                        WHERE r.organization_id=scoped_org AND r.synthetic=e.synthetic
                            AND e.occurred_at >= r.window_start AND e.occurred_at <= r.window_end
                    )
                ORDER BY e.occurred_at,e.id LIMIT batch_size FOR UPDATE OF e SKIP LOCKED
            ) selected;
            IF candidates IS NULL THEN RETURN 0; END IF;
            DELETE FROM public.anomalies WHERE organization_id=scoped_org AND event_id=ANY(candidates);
            DELETE FROM public.security_events WHERE organization_id=scoped_org AND id=ANY(candidates);
            GET DIAGNOSTICS removed = ROW_COUNT;
            RETURN removed;
        END;
        $mesh_retention$;
        """)
        op.execute(
            "REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM PUBLIC"
        )


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
