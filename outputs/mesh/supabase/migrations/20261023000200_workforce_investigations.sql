-- Running upgrade 0003 -> 0004

CREATE TABLE job_roles (
    title VARCHAR(100) NOT NULL, 
    grade VARCHAR(40) NOT NULL, 
    version INTEGER NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    minimum_base NUMERIC(14, 2) NOT NULL, 
    maximum_base NUMERIC(14, 2) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (version > 0 AND minimum_base >= 0 AND maximum_base >= minimum_base), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, title, grade, version)
);

CREATE INDEX ix_job_roles_organization_id ON job_roles (organization_id);

CREATE TABLE incident_notes (
    incident_id VARCHAR(36) NOT NULL, 
    author_id VARCHAR(36) NOT NULL, 
    body VARCHAR(4000) NOT NULL, 
    reference VARCHAR(200), 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, author_id) REFERENCES memberships (organization_id, user_id), 
    FOREIGN KEY(organization_id, incident_id) REFERENCES incidents (organization_id, id)
);

CREATE INDEX ix_incident_notes_organization_id ON incident_notes (organization_id);

CREATE TABLE employment_changes (
    employee_id VARCHAR(36) NOT NULL, 
    job_role_id VARCHAR(36) NOT NULL, 
    previous_terms_id VARCHAR(36), 
    base NUMERIC(14, 2) NOT NULL, 
    effective_on DATE NOT NULL, 
    reason VARCHAR(1000) NOT NULL, 
    proposed_by VARCHAR(36) NOT NULL, 
    reviewed_by VARCHAR(36), 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('proposed','approved','rejected','applied')), 
    CHECK (base >= 0), 
    FOREIGN KEY(organization_id, employee_id) REFERENCES employees (organization_id, id), 
    FOREIGN KEY(organization_id, job_role_id) REFERENCES job_roles (organization_id, id), 
    UNIQUE (organization_id, id)
);

CREATE INDEX ix_employment_changes_organization_id ON employment_changes (organization_id);

CREATE TABLE leave_entitlements (
    employee_id VARCHAR(36) NOT NULL, 
    year INTEGER NOT NULL, 
    allowance_days INTEGER NOT NULL, 
    counting VARCHAR(20) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (counting IN ('calendar','weekdays')), 
    CHECK (year BETWEEN 2000 AND 2200 AND allowance_days BETWEEN 0 AND 366), 
    FOREIGN KEY(organization_id, employee_id) REFERENCES employees (organization_id, id), 
    UNIQUE (organization_id, employee_id, year)
);

CREATE INDEX ix_leave_entitlements_organization_id ON leave_entitlements (organization_id);

CREATE TABLE employment_terms (
    employee_id VARCHAR(36) NOT NULL, 
    job_role_id VARCHAR(36) NOT NULL, 
    change_id VARCHAR(36) NOT NULL, 
    base NUMERIC(14, 2) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    effective_on DATE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (base >= 0), 
    FOREIGN KEY(organization_id, change_id) REFERENCES employment_changes (organization_id, id), 
    FOREIGN KEY(organization_id, employee_id) REFERENCES employees (organization_id, id), 
    FOREIGN KEY(organization_id, job_role_id) REFERENCES job_roles (organization_id, id), 
    UNIQUE (change_id), 
    UNIQUE (organization_id, employee_id, effective_on)
);

CREATE INDEX ix_employment_terms_organization_id ON employment_terms (organization_id);

ALTER TABLE "job_roles" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "job_roles" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "job_roles"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public."job_roles" FROM anon;
                END IF;
            END; $mesh_grants$;;

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public."job_roles" FROM authenticated;
                END IF;
            END; $mesh_grants$;;

ALTER TABLE "employment_changes" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "employment_changes" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "employment_changes"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public."employment_changes" FROM anon;
                END IF;
            END; $mesh_grants$;;

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public."employment_changes" FROM authenticated;
                END IF;
            END; $mesh_grants$;;

ALTER TABLE "employment_terms" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "employment_terms" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "employment_terms"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public."employment_terms" FROM anon;
                END IF;
            END; $mesh_grants$;;

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public."employment_terms" FROM authenticated;
                END IF;
            END; $mesh_grants$;;

ALTER TABLE "leave_entitlements" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "leave_entitlements" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "leave_entitlements"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public."leave_entitlements" FROM anon;
                END IF;
            END; $mesh_grants$;;

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public."leave_entitlements" FROM authenticated;
                END IF;
            END; $mesh_grants$;;

ALTER TABLE "incident_notes" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "incident_notes" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "incident_notes"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public."incident_notes" FROM anon;
                END IF;
            END; $mesh_grants$;;

DO $mesh_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public."incident_notes" FROM authenticated;
                END IF;
            END; $mesh_grants$;;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON job_roles FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON employment_terms FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON incident_notes FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON payroll_calculations FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';


