BEGIN;

-- Running upgrade 0024 -> 0025

CREATE TABLE ai_requests (
    requested_by VARCHAR(36) NOT NULL, 
    purpose VARCHAR(30) NOT NULL, 
    provider VARCHAR(50) NOT NULL, 
    model VARCHAR(100) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    policy_snapshot JSON NOT NULL, 
    context_digest VARCHAR(64) NOT NULL, 
    endpoint_digest VARCHAR(64) NOT NULL, 
    period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    reserved_input_units INTEGER NOT NULL, 
    reserved_output_units INTEGER NOT NULL, 
    reserved_cost NUMERIC(14, 6), 
    currency VARCHAR(3), 
    dispatch_token VARCHAR(36), 
    dispatch_deadline TIMESTAMP WITH TIME ZONE NOT NULL, 
    dispatched_at TIMESTAMP WITH TIME ZONE, 
    settled_at TIMESTAMP WITH TIME ZONE, 
    observed_input_units INTEGER, 
    observed_output_units INTEGER, 
    observed_cost NUMERIC(14, 6), 
    observed_currency VARCHAR(3), 
    reconciliation_digest VARCHAR(64), 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_ai_request_cancelled_unsent CHECK (status != 'cancelled' OR dispatch_token IS NULL), 
    CONSTRAINT ck_ai_request_currency_pairs CHECK ((reserved_cost IS NULL) = (currency IS NULL) AND (observed_cost IS NULL) = (observed_currency IS NULL)), 
    CONSTRAINT ck_ai_request_digests CHECK (length(context_digest)=64 AND length(endpoint_digest)=64), 
    CONSTRAINT ck_ai_request_dispatch_marker CHECK (status NOT IN ('dispatched','succeeded','ambiguous','reconciled_charge','reconciled_no_charge') OR (dispatch_token IS NOT NULL AND dispatched_at IS NOT NULL)), 
    CONSTRAINT ck_ai_request_dispatch_pair CHECK ((dispatch_token IS NULL) = (dispatched_at IS NULL)), 
    CONSTRAINT ck_ai_request_no_early_observation CHECK (status NOT IN ('reserved','dispatched') OR (observed_input_units IS NULL AND observed_output_units IS NULL AND observed_cost IS NULL AND observed_currency IS NULL)), 
    CONSTRAINT ck_ai_request_observed_cost CHECK (observed_cost IS NULL OR observed_cost >= 0), 
    CONSTRAINT ck_ai_request_observed_input CHECK (observed_input_units IS NULL OR observed_input_units >= 0), 
    CONSTRAINT ck_ai_request_observed_output CHECK (observed_output_units IS NULL OR observed_output_units >= 0), 
    CONSTRAINT ck_ai_request_observed_units CHECK (status NOT IN ('succeeded','reconciled_charge') OR (observed_input_units IS NOT NULL AND observed_output_units IS NOT NULL)), 
    CONSTRAINT ck_ai_request_reconciled_charge CHECK (status != 'reconciled_charge' OR (observed_cost IS NOT NULL AND observed_currency IS NOT NULL)), 
    CONSTRAINT ck_ai_request_reconciliation_state CHECK ((status IN ('reconciled_charge','reconciled_no_charge')) = (reconciliation_digest IS NOT NULL)), 
    CONSTRAINT ck_ai_request_reserve_cost CHECK (reserved_cost IS NULL OR reserved_cost >= 0), 
    CONSTRAINT ck_ai_request_reserve_units CHECK (reserved_input_units >= 0 AND reserved_output_units >= 0), 
    CONSTRAINT ck_ai_request_settlement_state CHECK (((status IN ('reserved','dispatched','ambiguous')) AND settled_at IS NULL) OR ((status NOT IN ('reserved','dispatched','ambiguous')) AND settled_at IS NOT NULL)), 
    CONSTRAINT ck_ai_request_status CHECK (status IN ('reserved','dispatched','succeeded','ambiguous','not_dispatched','cancelled','reconciled_charge','reconciled_no_charge')), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, id), 
    CONSTRAINT uq_ai_request_admission_period UNIQUE (organization_id, id, period_start)
);

CREATE INDEX ix_ai_request_org_period_status ON ai_requests (organization_id, period_start, status);

CREATE INDEX ix_ai_requests_organization_id ON ai_requests (organization_id);

CREATE TABLE ai_request_events (
    request_id VARCHAR(36) NOT NULL, 
    position INTEGER NOT NULL, 
    actor_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(40) NOT NULL, 
    details JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_ai_request_event_position CHECK (position > 0), 
    FOREIGN KEY(organization_id, request_id) REFERENCES ai_requests (organization_id, id), 
    UNIQUE (organization_id, request_id, position)
);

CREATE INDEX ix_ai_request_event_scope ON ai_request_events (organization_id, request_id);

CREATE INDEX ix_ai_request_events_organization_id ON ai_request_events (organization_id);

ALTER TABLE ai_usage ADD COLUMN request_id VARCHAR(36);

ALTER TABLE ai_usage ADD COLUMN admission_period_start TIMESTAMP WITH TIME ZONE;

ALTER TABLE ai_usage ADD CONSTRAINT fk_ai_usage_request_period FOREIGN KEY(organization_id, request_id, admission_period_start) REFERENCES ai_requests (organization_id, id, period_start);

ALTER TABLE ai_usage ADD CONSTRAINT uq_ai_usage_request UNIQUE (organization_id, request_id);

ALTER TABLE ai_usage ADD CONSTRAINT ck_ai_usage_request_period_pair CHECK ((request_id IS NULL) = (admission_period_start IS NULL));

ALTER TABLE "ai_requests" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "ai_requests" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "ai_requests"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

REVOKE ALL ON TABLE ai_requests FROM PUBLIC;

ALTER TABLE "ai_request_events" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "ai_request_events" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "ai_request_events"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

REVOKE ALL ON TABLE ai_request_events FROM PUBLIC;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON ai_request_events FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON ai_usage FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER no_ai_request_delete BEFORE DELETE ON ai_requests FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE FUNCTION public.mesh_guard_ai_request() RETURNS trigger
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
        END $guard$;

CREATE TRIGGER ai_request_guard BEFORE UPDATE ON ai_requests FOR EACH ROW EXECUTE FUNCTION public.mesh_guard_ai_request();

REVOKE ALL ON FUNCTION public.mesh_guard_ai_request() FROM PUBLIC;

DO $ai_acl$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                REVOKE ALL ON TABLE ai_requests,ai_request_events FROM anon;
                REVOKE ALL ON FUNCTION public.mesh_guard_ai_request() FROM anon;
            END IF; END $ai_acl$;;

DO $ai_acl$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                REVOKE ALL ON TABLE ai_requests,ai_request_events FROM authenticated;
                REVOKE ALL ON FUNCTION public.mesh_guard_ai_request() FROM authenticated;
            END IF; END $ai_acl$;;

DO $ai_acl$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
                REVOKE ALL ON TABLE ai_requests,ai_request_events FROM service_role;
                REVOKE ALL ON FUNCTION public.mesh_guard_ai_request() FROM service_role;
            END IF; END $ai_acl$;;

DO $ai_runtime$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
            GRANT SELECT,INSERT,UPDATE ON TABLE ai_requests TO mesh_runtime;
            GRANT SELECT,INSERT ON TABLE ai_request_events TO mesh_runtime;
            REVOKE DELETE ON TABLE ai_requests FROM mesh_runtime;
            REVOKE UPDATE,DELETE ON TABLE ai_usage,ai_request_events FROM mesh_runtime;
        END IF; END $ai_runtime$;;

UPDATE alembic_version SET version_num='0025' WHERE alembic_version.version_num = '0024';

COMMIT;

