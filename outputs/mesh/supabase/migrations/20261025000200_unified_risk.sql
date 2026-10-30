BEGIN;

-- Running upgrade 0013 -> 0014

CREATE INDEX ix_event_org_time_id ON security_events (organization_id, occurred_at, id);

CREATE TABLE risk_policies (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    version INTEGER NOT NULL, 
    created_by VARCHAR(36) NOT NULL, 
    algorithm_version VARCHAR(40) NOT NULL, 
    weights JSON NOT NULL, 
    thresholds JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, created_by) REFERENCES memberships (organization_id, user_id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, version), 
    CHECK (version > 0)
);

CREATE TABLE risk_assessments (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    policy_id VARCHAR(36) NOT NULL, 
    requested_by VARCHAR(36) NOT NULL, 
    request_key VARCHAR(100) NOT NULL, 
    request_digest VARCHAR(64) NOT NULL, 
    window_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    window_end TIMESTAMP WITH TIME ZONE NOT NULL, 
    synthetic BOOLEAN NOT NULL, 
    result JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, policy_id) REFERENCES risk_policies (organization_id, id), 
    FOREIGN KEY(organization_id, requested_by) REFERENCES memberships (organization_id, user_id), 
    UNIQUE (organization_id, request_key), 
    CHECK (window_start <= window_end)
);

CREATE INDEX ix_risk_assessment_window ON risk_assessments (organization_id, synthetic, window_end, window_start);

CREATE INDEX ix_risk_policies_organization_id ON risk_policies (organization_id);

REVOKE ALL ON TABLE public."risk_policies" FROM PUBLIC;

ALTER TABLE "risk_policies" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "risk_policies" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "risk_policies"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON risk_policies FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_risk$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                        REVOKE ALL ON TABLE public."risk_policies" FROM anon;
                    END IF;
                END; $mesh_risk$;;

DO $mesh_risk$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                        REVOKE ALL ON TABLE public."risk_policies" FROM authenticated;
                    END IF;
                END; $mesh_risk$;;

DO $mesh_risk_runtime$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                    GRANT SELECT, INSERT ON TABLE public."risk_policies" TO mesh_runtime;
                    REVOKE UPDATE, DELETE ON TABLE public."risk_policies" FROM mesh_runtime;
                END IF;
            END; $mesh_risk_runtime$;;

CREATE INDEX ix_risk_assessments_organization_id ON risk_assessments (organization_id);

REVOKE ALL ON TABLE public."risk_assessments" FROM PUBLIC;

ALTER TABLE "risk_assessments" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "risk_assessments" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "risk_assessments"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON risk_assessments FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_risk$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                        REVOKE ALL ON TABLE public."risk_assessments" FROM anon;
                    END IF;
                END; $mesh_risk$;;

DO $mesh_risk$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                        REVOKE ALL ON TABLE public."risk_assessments" FROM authenticated;
                    END IF;
                END; $mesh_risk$;;

DO $mesh_risk_runtime$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                    GRANT SELECT, INSERT ON TABLE public."risk_assessments" TO mesh_runtime;
                    REVOKE UPDATE, DELETE ON TABLE public."risk_assessments" FROM mesh_runtime;
                END IF;
            END; $mesh_risk_runtime$;;

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
        $mesh_retention$;;

REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM PUBLIC;

UPDATE alembic_version SET version_num='0014' WHERE alembic_version.version_num = '0013';

COMMIT;

