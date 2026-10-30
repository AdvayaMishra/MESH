BEGIN;

-- Running upgrade 0026 -> 0027

CREATE TABLE billing_collections (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    requested_by VARCHAR(36) NOT NULL, 
    requested_session_id VARCHAR(36), 
    requested_aal VARCHAR(4) NOT NULL, 
    request_key VARCHAR(36) NOT NULL, 
    period VARCHAR(7) NOT NULL, 
    provider_account_id VARCHAR(12) NOT NULL, 
    binding_revision VARCHAR(64) NOT NULL, 
    synthetic BOOLEAN NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    attempts INTEGER NOT NULL, 
    dispatch_token VARCHAR(36), 
    dispatched_at TIMESTAMP WITH TIME ZONE, 
    lease_until TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    error_code VARCHAR(50), 
    report JSON, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(organization_id, requested_by) REFERENCES memberships (organization_id, user_id), 
    FOREIGN KEY(requested_by, requested_session_id) REFERENCES identity_sessions (user_id, provider_session_id), 
    CONSTRAINT uq_billing_collection_request UNIQUE (organization_id, request_key), 
    CONSTRAINT ck_billing_collection_status CHECK (status IN ('queued','running','completed','failed','ambiguous','cancelled')), 
    CONSTRAINT ck_billing_collection_attempts CHECK (attempts >= 0 AND attempts <= 1), 
    CONSTRAINT ck_billing_collection_aal CHECK (requested_aal IN ('aal1','aal2')), 
    CONSTRAINT ck_billing_collection_identity CHECK (length(request_key)=36 AND length(binding_revision)=64 AND length(provider_account_id)=12 AND length(period)=7), 
    CONSTRAINT ck_billing_collection_dispatch_pair CHECK ((dispatch_token IS NULL) = (dispatched_at IS NULL)), 
    CONSTRAINT ck_billing_collection_dispatch_attempt CHECK ((attempts=0 AND dispatch_token IS NULL) OR (attempts=1 AND dispatch_token IS NOT NULL)), 
    CONSTRAINT ck_billing_collection_lifecycle CHECK ((status='queued' AND attempts=0 AND lease_until IS NULL AND finished_at IS NULL) OR (status='running' AND attempts=1 AND lease_until IS NOT NULL AND finished_at IS NULL) OR (status IN ('completed','failed','ambiguous','cancelled') AND lease_until IS NULL AND finished_at IS NOT NULL)), 
    CONSTRAINT ck_billing_collection_result CHECK ((status='completed' AND report IS NOT NULL AND error_code IS NULL) OR (status!='completed' AND report IS NULL)), 
    CONSTRAINT ck_billing_collection_terminal_dispatch CHECK (status NOT IN ('completed','failed','ambiguous') OR attempts=1)
);

CREATE INDEX ix_billing_collections_organization_id ON billing_collections (organization_id);

CREATE INDEX ix_billing_collection_queue ON billing_collections (organization_id, status, created_at);

ALTER TABLE "billing_collections" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "billing_collections" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "billing_collections"
        USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
        WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

ALTER TABLE billing_collections ADD CONSTRAINT ck_billing_report_scope CHECK (
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
      ));

CREATE FUNCTION mesh_guard_billing_collection() RETURNS trigger LANGUAGE plpgsql
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
      END $$;

CREATE TRIGGER billing_collection_guard BEFORE INSERT OR UPDATE ON billing_collections FOR EACH ROW EXECUTE FUNCTION mesh_guard_billing_collection();

CREATE TRIGGER no_billing_collection_delete BEFORE DELETE ON billing_collections FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

REVOKE ALL ON TABLE billing_collections FROM PUBLIC;

REVOKE ALL ON FUNCTION mesh_guard_billing_collection() FROM PUBLIC;

DO $billing_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON TABLE billing_collections FROM anon;
            REVOKE ALL ON FUNCTION mesh_guard_billing_collection() FROM anon;
          END IF;
        END $billing_acl$;

DO $billing_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON TABLE billing_collections FROM authenticated;
            REVOKE ALL ON FUNCTION mesh_guard_billing_collection() FROM authenticated;
          END IF;
        END $billing_acl$;

DO $billing_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
            REVOKE ALL ON TABLE billing_collections FROM service_role;
            REVOKE ALL ON FUNCTION mesh_guard_billing_collection() FROM service_role;
          END IF;
        END $billing_acl$;

DO $billing_runtime$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON TABLE billing_collections TO mesh_runtime;
        REVOKE DELETE ON TABLE billing_collections FROM mesh_runtime;
      END IF;
    END $billing_runtime$;

UPDATE alembic_version SET version_num='0027' WHERE alembic_version.version_num = '0026';

COMMIT;

