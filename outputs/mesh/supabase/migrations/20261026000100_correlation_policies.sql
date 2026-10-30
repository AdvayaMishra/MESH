BEGIN;

-- Running upgrade 0023 -> 0024

CREATE TABLE correlation_policies (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    version INTEGER NOT NULL, 
    created_by VARCHAR(36) NOT NULL, 
    algorithm_version VARCHAR(40) NOT NULL, 
    configuration JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, created_by) REFERENCES memberships (organization_id, user_id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, version), 
    CONSTRAINT ck_correlation_policy_version CHECK (version > 0)
);

CREATE INDEX ix_correlation_policies_organization_id ON correlation_policies (organization_id);

ALTER TABLE incidents ADD COLUMN correlation_policy_id VARCHAR(36);

ALTER TABLE incidents ADD COLUMN correlation_snapshot JSON;

ALTER TABLE incidents ADD CONSTRAINT fk_incident_correlation_policy FOREIGN KEY(organization_id, correlation_policy_id) REFERENCES correlation_policies (organization_id, id);

ALTER TABLE incidents ADD CONSTRAINT ck_incident_correlation_snapshot CHECK (correlation_policy_id IS NULL OR correlation_snapshot IS NOT NULL);

CREATE INDEX ix_incident_org_correlation_policy ON incidents (organization_id, correlation_policy_id);

ALTER TABLE "correlation_policies" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "correlation_policies" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "correlation_policies"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON correlation_policies FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER correlation_snapshot_immutable BEFORE UPDATE OF correlation_policy_id,correlation_snapshot ON incidents FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

REVOKE ALL ON TABLE correlation_policies FROM PUBLIC;

DO $correlation_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE correlation_policies FROM anon;
                END IF;
            END $correlation_acl$;;

DO $correlation_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE correlation_policies FROM authenticated;
                END IF;
            END $correlation_acl$;;

DO $correlation_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
                    REVOKE ALL ON TABLE correlation_policies FROM service_role;
                END IF;
            END $correlation_acl$;;

DO $correlation_runtime$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                GRANT SELECT,INSERT ON TABLE correlation_policies TO mesh_runtime;
                REVOKE UPDATE,DELETE ON TABLE correlation_policies FROM mesh_runtime;
            END IF;
        END $correlation_runtime$;;

UPDATE alembic_version SET version_num='0024' WHERE alembic_version.version_num = '0023';

COMMIT;

