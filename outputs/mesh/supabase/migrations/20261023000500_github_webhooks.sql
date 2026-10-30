-- Running upgrade 0006 -> 0007

CREATE TABLE webhook_deliveries (
    provider VARCHAR(30) NOT NULL, 
    delivery_id VARCHAR(36) NOT NULL, 
    event VARCHAR(50) NOT NULL, 
    payload_digest VARCHAR(64) NOT NULL, 
    result JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, provider, delivery_id), 
    UNIQUE (organization_id, provider, payload_digest)
);

CREATE INDEX ix_webhook_deliveries_organization_id ON webhook_deliveries (organization_id);

ALTER TABLE "webhook_deliveries" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "webhook_deliveries" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "webhook_deliveries"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON webhook_deliveries FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_webhook_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public.webhook_deliveries FROM anon;
                END IF;
            END; $mesh_webhook_grants$;;

DO $mesh_webhook_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public.webhook_deliveries FROM authenticated;
                END IF;
            END; $mesh_webhook_grants$;;

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';


