-- Running upgrade 0009 -> 0010

CREATE UNIQUE INDEX uq_cloud_assessments_org_id ON cloud_assessments (organization_id, id);

CREATE TABLE cloud_assessment_jobs (
    requested_by VARCHAR(36) NOT NULL, 
    request_key VARCHAR(100) NOT NULL, 
    provider VARCHAR(20) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    attempts INTEGER NOT NULL, 
    lease_until TIMESTAMP WITH TIME ZONE, 
    assessment_id VARCHAR(36), 
    error_code VARCHAR(50), 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, requested_by) REFERENCES memberships (organization_id, user_id), 
    FOREIGN KEY(organization_id, assessment_id) REFERENCES cloud_assessments (organization_id, id), 
    UNIQUE (organization_id, request_key), 
    CHECK (status IN ('queued','running','completed','dead_letter','cancelled')), 
    CHECK (attempts >= 0 AND attempts <= 3)
);

CREATE INDEX ix_cloud_assessment_jobs_organization_id ON cloud_assessment_jobs (organization_id);

ALTER TABLE "cloud_assessment_jobs" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "cloud_assessment_jobs" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "cloud_assessment_jobs"
            USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

DO $mesh_cloud_job_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public.cloud_assessment_jobs FROM anon;
                END IF;
            END; $mesh_cloud_job_grants$;;

DO $mesh_cloud_job_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public.cloud_assessment_jobs FROM authenticated;
                END IF;
            END; $mesh_cloud_job_grants$;;

UPDATE alembic_version SET version_num='0010' WHERE alembic_version.version_num = '0009';


