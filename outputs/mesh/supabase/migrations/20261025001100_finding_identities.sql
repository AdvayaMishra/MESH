BEGIN;

-- Running upgrade 0022 -> 0023

CREATE TABLE finding_identities (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    repository_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    fingerprint VARCHAR(64) NOT NULL, 
    algorithm_version VARCHAR(50) NOT NULL, 
    match_metadata JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, repository_id) REFERENCES repositories (organization_id, id), 
    CONSTRAINT uq_finding_identity_fingerprint UNIQUE (organization_id, repository_id, fingerprint), 
    CONSTRAINT uq_finding_identity_scope UNIQUE (organization_id, repository_id, id), 
    CONSTRAINT ck_finding_identity_fingerprint_length CHECK (length(fingerprint)=64)
);

CREATE INDEX ix_finding_identities_organization_id ON finding_identities (organization_id);

CREATE INDEX ix_finding_identity_org_repository ON finding_identities (organization_id, repository_id);

ALTER TABLE findings ADD COLUMN identity_id VARCHAR(36);

ALTER TABLE findings ADD CONSTRAINT fk_finding_identity_scope FOREIGN KEY(organization_id, repository_id, identity_id) REFERENCES finding_identities (organization_id, repository_id, id);

CREATE INDEX ix_finding_org_repository_identity ON findings (organization_id, repository_id, identity_id);

ALTER TABLE "finding_identities" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "finding_identities" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "finding_identities"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON finding_identities FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

REVOKE ALL ON TABLE finding_identities FROM PUBLIC;

DO $identity_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE finding_identities FROM anon;
                END IF;
            END $identity_acl$;;

DO $identity_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE finding_identities FROM authenticated;
                END IF;
            END $identity_acl$;;

DO $identity_acl$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
                    REVOKE ALL ON TABLE finding_identities FROM service_role;
                END IF;
            END $identity_acl$;;

DO $identity_runtime$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                GRANT SELECT,INSERT ON TABLE finding_identities TO mesh_runtime;
                REVOKE UPDATE,DELETE ON TABLE finding_identities FROM mesh_runtime;
            END IF;
        END $identity_runtime$;;

UPDATE alembic_version SET version_num='0023' WHERE alembic_version.version_num = '0022';

COMMIT;

