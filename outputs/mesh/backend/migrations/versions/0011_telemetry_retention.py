"""Narrow, bounded telemetry retirement; investigation evidence is always preserved."""

from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE FUNCTION public.mesh_retire_telemetry(retention_days integer, batch_size integer)
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
    op.execute("REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM PUBLIC")


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
