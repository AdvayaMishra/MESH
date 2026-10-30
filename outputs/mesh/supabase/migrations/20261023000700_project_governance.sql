-- Running upgrade 0008 -> 0009

ALTER TABLE projects ADD COLUMN approval_policy JSON;

CREATE TABLE project_approval_policies (
    version INTEGER NOT NULL, 
    required_senior_reviews INTEGER NOT NULL, 
    reviewers_must_be_members BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, version), 
    CHECK (version > 0 AND required_senior_reviews BETWEEN 1 AND 5)
);

CREATE INDEX ix_project_approval_policies_organization_id ON project_approval_policies (organization_id);

CREATE TABLE project_reviews (
    project_id VARCHAR(36) NOT NULL, 
    reviewer_id VARCHAR(36) NOT NULL, 
    comment VARCHAR(2000) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, project_id) REFERENCES projects (organization_id, id), 
    FOREIGN KEY(organization_id, reviewer_id) REFERENCES memberships (organization_id, user_id), 
    UNIQUE (organization_id, project_id, reviewer_id)
);

CREATE INDEX ix_project_reviews_organization_id ON project_reviews (organization_id);

ALTER TABLE "project_approval_policies" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "project_approval_policies" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "project_approval_policies"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON project_approval_policies FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_project_grants$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                        REVOKE ALL ON TABLE public."project_approval_policies" FROM anon;
                    END IF;
                END; $mesh_project_grants$;;

DO $mesh_project_grants$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                        REVOKE ALL ON TABLE public."project_approval_policies" FROM authenticated;
                    END IF;
                END; $mesh_project_grants$;;

ALTER TABLE "project_reviews" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "project_reviews" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "project_reviews"
                USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON project_reviews FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_project_grants$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                        REVOKE ALL ON TABLE public."project_reviews" FROM anon;
                    END IF;
                END; $mesh_project_grants$;;

DO $mesh_project_grants$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                        REVOKE ALL ON TABLE public."project_reviews" FROM authenticated;
                    END IF;
                END; $mesh_project_grants$;;

UPDATE alembic_version SET version_num='0009' WHERE alembic_version.version_num = '0008';


