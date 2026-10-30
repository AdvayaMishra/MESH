BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE organizations (
    id VARCHAR(36) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    status VARCHAR NOT NULL, 
    verification_status VARCHAR NOT NULL, 
    domain VARCHAR(253), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (domain)
);

CREATE TABLE audit_logs (
    actor_id VARCHAR(36) NOT NULL, 
    action VARCHAR(100) NOT NULL, 
    target_id VARCHAR(100) NOT NULL, 
    outcome VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_audit_logs_organization_id ON audit_logs (organization_id);

CREATE TABLE deliveries (
    message_id VARCHAR(36) NOT NULL, 
    consumer VARCHAR(100) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, message_id, consumer)
);

CREATE INDEX ix_deliveries_organization_id ON deliveries (organization_id);

CREATE TABLE domain_challenges (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    domain VARCHAR(253) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    attempts INTEGER NOT NULL, 
    status VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_domain_challenges_organization_id ON domain_challenges (organization_id);

CREATE TABLE incidents (
    actor_id VARCHAR(100) NOT NULL, 
    fingerprint VARCHAR(64) NOT NULL, 
    event_ids JSON NOT NULL, 
    risk INTEGER NOT NULL, 
    explanation VARCHAR(1000) NOT NULL, 
    status VARCHAR NOT NULL, 
    synthetic BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, fingerprint), 
    UNIQUE (organization_id, id)
);

CREATE INDEX ix_incidents_organization_id ON incidents (organization_id);

CREATE TABLE invitations (
    email VARCHAR(254) NOT NULL, 
    role VARCHAR(30) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    creator_id VARCHAR(36) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    accepted_at TIMESTAMP WITH TIME ZONE, 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (token_hash)
);

CREATE INDEX ix_invitations_organization_id ON invitations (organization_id);

CREATE TABLE memberships (
    organization_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    role VARCHAR(30) NOT NULL, 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (organization_id, user_id), 
    CHECK (role IN ('owner','hr','senior_developer','junior_developer','security_analyst')), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, email)
);

CREATE TABLE outbox (
    topic VARCHAR(100) NOT NULL, 
    payload JSON NOT NULL, 
    attempts INTEGER NOT NULL, 
    available_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_outbox_organization_id ON outbox (organization_id);

CREATE TABLE projects (
    name VARCHAR(200) NOT NULL, 
    description VARCHAR(4000) NOT NULL, 
    proposer_id VARCHAR(36) NOT NULL, 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('proposed','reviewed','approved','rejected')), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, id)
);

CREATE INDEX ix_projects_organization_id ON projects (organization_id);

CREATE TABLE repositories (
    full_name VARCHAR(200) NOT NULL, 
    installation_id INTEGER NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, full_name), 
    UNIQUE (organization_id, id)
);

CREATE INDEX ix_repositories_organization_id ON repositories (organization_id);

CREATE TABLE security_events (
    source_id VARCHAR(150) NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    actor_id VARCHAR(100) NOT NULL, 
    category VARCHAR(50) NOT NULL, 
    action VARCHAR(80) NOT NULL, 
    result VARCHAR(30) NOT NULL, 
    count INTEGER NOT NULL, 
    synthetic BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, source_id)
);

CREATE INDEX ix_event_actor_time ON security_events (organization_id, actor_id, occurred_at);

CREATE INDEX ix_security_events_organization_id ON security_events (organization_id);

CREATE TABLE anomalies (
    event_id VARCHAR(36) NOT NULL, 
    rule VARCHAR(80) NOT NULL, 
    weight INTEGER NOT NULL, 
    explanation VARCHAR(500) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, event_id) REFERENCES security_events (organization_id, id), 
    UNIQUE (organization_id, event_id, rule)
);

CREATE INDEX ix_anomalies_organization_id ON anomalies (organization_id);

CREATE TABLE employees (
    user_id VARCHAR(36) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    department VARCHAR(100) NOT NULL, 
    status VARCHAR NOT NULL, 
    verification_status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, user_id) REFERENCES memberships (organization_id, user_id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, user_id)
);

CREATE INDEX ix_employees_organization_id ON employees (organization_id);

CREATE TABLE findings (
    repository_id VARCHAR(36) NOT NULL, 
    scanner VARCHAR(30) NOT NULL, 
    rule_id VARCHAR(200) NOT NULL, 
    severity VARCHAR(20) NOT NULL, 
    file_path VARCHAR(500) NOT NULL, 
    line INTEGER NOT NULL, 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, repository_id) REFERENCES repositories (organization_id, id)
);

CREATE INDEX ix_findings_organization_id ON findings (organization_id);

CREATE TABLE response_actions (
    incident_id VARCHAR(36) NOT NULL, 
    action VARCHAR(50) NOT NULL, 
    proposed_by VARCHAR(36) NOT NULL, 
    approved_by VARCHAR(36), 
    status VARCHAR NOT NULL, 
    mode VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, incident_id) REFERENCES incidents (organization_id, id)
);

CREATE INDEX ix_response_actions_organization_id ON response_actions (organization_id);

CREATE TABLE tasks (
    project_id VARCHAR(36) NOT NULL, 
    assignee_id VARCHAR(36) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, assignee_id) REFERENCES memberships (organization_id, user_id), 
    FOREIGN KEY(organization_id, project_id) REFERENCES projects (organization_id, id)
);

CREATE INDEX ix_tasks_organization_id ON tasks (organization_id);

CREATE TABLE trust_events (
    user_id VARCHAR(36) NOT NULL, 
    reference VARCHAR(100) NOT NULL, 
    delta INTEGER NOT NULL, 
    reason VARCHAR(500) NOT NULL, 
    reviewed_by VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (delta BETWEEN -10 AND 10), 
    FOREIGN KEY(organization_id, user_id) REFERENCES memberships (organization_id, user_id), 
    UNIQUE (organization_id, reference)
);

CREATE INDEX ix_trust_events_organization_id ON trust_events (organization_id);

CREATE TABLE payroll (
    employee_id VARCHAR(36) NOT NULL, 
    period VARCHAR(7) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    gross NUMERIC(14, 2) NOT NULL, 
    deductions NUMERIC(14, 2) NOT NULL, 
    net NUMERIC(14, 2) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (gross >= 0 AND deductions >= 0 AND net >= 0 AND net = gross - deductions), 
    FOREIGN KEY(organization_id, employee_id) REFERENCES employees (organization_id, id), 
    UNIQUE (organization_id, employee_id, period)
);

CREATE INDEX ix_payroll_organization_id ON payroll (organization_id);

ALTER TABLE "organizations" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "organizations" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "organizations"
            USING (id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "audit_logs" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "audit_logs" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "audit_logs"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "deliveries" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "deliveries" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "deliveries"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "domain_challenges" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "domain_challenges" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "domain_challenges"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "incidents" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "incidents" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "incidents"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "invitations" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "invitations" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "invitations"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "memberships" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "memberships" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "memberships"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "outbox" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "outbox" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "outbox"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "projects" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "projects" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "projects"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "repositories" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "repositories" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "repositories"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "security_events" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "security_events" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "security_events"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "anomalies" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "anomalies" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "anomalies"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "employees" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "employees" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "employees"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "findings" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "findings" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "findings"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "response_actions" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "response_actions" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "response_actions"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "tasks" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "tasks" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "tasks"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "trust_events" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "trust_events" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "trust_events"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "payroll" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "payroll" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "payroll"
            USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
            WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

CREATE FUNCTION mesh_deny_ledger_mutation() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only ledger'; END; $$;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON trust_events FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE UNIQUE INDEX uq_tasks_org_id ON tasks (organization_id, id);

ALTER TABLE security_events ADD COLUMN session_id VARCHAR(100);

ALTER TABLE security_events ADD COLUMN resource_id VARCHAR(100);

CREATE TABLE ai_usage (
    provider VARCHAR(50) NOT NULL, 
    purpose VARCHAR(30) NOT NULL, 
    input_units INTEGER NOT NULL, 
    output_units INTEGER NOT NULL, 
    estimated_cost NUMERIC(14, 6), 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_ai_usage_organization_id ON ai_usage (organization_id);

CREATE TABLE budgets (
    period VARCHAR(7) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    amount NUMERIC(14, 2) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (amount >= 0), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, period, currency)
);

CREATE INDEX ix_budgets_organization_id ON budgets (organization_id);

CREATE TABLE cloud_assessments (
    provider VARCHAR NOT NULL, 
    findings JSON NOT NULL, 
    partial BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_cloud_assessments_organization_id ON cloud_assessments (organization_id);

CREATE TABLE cost_records (
    period VARCHAR(7) NOT NULL, 
    department VARCHAR(100) NOT NULL, 
    category VARCHAR(30) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    amount NUMERIC(14, 2) NOT NULL, 
    source VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (amount >= 0), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_cost_records_organization_id ON cost_records (organization_id);

CREATE TABLE departments (
    name VARCHAR(100) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, name)
);

CREATE INDEX ix_departments_organization_id ON departments (organization_id);

CREATE TABLE detection_policies (
    thresholds JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id)
);

CREATE INDEX ix_detection_policies_organization_id ON detection_policies (organization_id);

CREATE TABLE audit_seals (
    audit_id VARCHAR(36) NOT NULL, 
    position INTEGER NOT NULL, 
    previous_hash VARCHAR(64) NOT NULL, 
    digest VARCHAR(64) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(audit_id) REFERENCES audit_logs (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (audit_id), 
    UNIQUE (organization_id, position)
);

CREATE INDEX ix_audit_seals_organization_id ON audit_seals (organization_id);

CREATE TABLE complaints (
    author_id VARCHAR(36) NOT NULL, 
    subject VARCHAR(200) NOT NULL, 
    body VARCHAR(4000) NOT NULL, 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, author_id) REFERENCES memberships (organization_id, user_id)
);

CREATE INDEX ix_complaints_organization_id ON complaints (organization_id);

CREATE TABLE incident_events (
    incident_id VARCHAR(36) NOT NULL, 
    event_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, event_id) REFERENCES security_events (organization_id, id), 
    FOREIGN KEY(organization_id, incident_id) REFERENCES incidents (organization_id, id), 
    UNIQUE (organization_id, incident_id, event_id)
);

CREATE INDEX ix_incident_events_organization_id ON incident_events (organization_id);

CREATE TABLE integration_accounts (
    user_id VARCHAR(36) NOT NULL, 
    provider VARCHAR(30) NOT NULL, 
    external_id VARCHAR(200) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, user_id) REFERENCES memberships (organization_id, user_id)
);

CREATE INDEX ix_integration_accounts_organization_id ON integration_accounts (organization_id);

CREATE TABLE project_comments (
    project_id VARCHAR(36) NOT NULL, 
    author_id VARCHAR(36) NOT NULL, 
    body VARCHAR(4000) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, project_id) REFERENCES projects (organization_id, id)
);

CREATE INDEX ix_project_comments_organization_id ON project_comments (organization_id);

CREATE TABLE project_members (
    project_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    manager BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, project_id) REFERENCES projects (organization_id, id), 
    FOREIGN KEY(organization_id, user_id) REFERENCES memberships (organization_id, user_id), 
    UNIQUE (organization_id, project_id, user_id)
);

CREATE INDEX ix_project_members_organization_id ON project_members (organization_id);

CREATE TABLE repository_projects (
    repository_id VARCHAR(36) NOT NULL, 
    project_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, project_id) REFERENCES projects (organization_id, id), 
    FOREIGN KEY(organization_id, repository_id) REFERENCES repositories (organization_id, id), 
    UNIQUE (organization_id, repository_id, project_id)
);

CREATE INDEX ix_repository_projects_organization_id ON repository_projects (organization_id);

CREATE TABLE scan_jobs (
    repository_id VARCHAR(36) NOT NULL, 
    requested_by VARCHAR(36) NOT NULL, 
    request_key VARCHAR(100) NOT NULL, 
    commit_sha VARCHAR(40) NOT NULL, 
    status VARCHAR NOT NULL, 
    attempts INTEGER NOT NULL, 
    lease_until TIMESTAMP WITH TIME ZONE, 
    report JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, repository_id) REFERENCES repositories (organization_id, id), 
    UNIQUE (organization_id, request_key)
);

CREATE INDEX ix_scan_jobs_organization_id ON scan_jobs (organization_id);

CREATE TABLE sprints (
    project_id VARCHAR(36) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    starts_on DATE NOT NULL, 
    ends_on DATE NOT NULL, 
    status VARCHAR NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (ends_on >= starts_on), 
    FOREIGN KEY(organization_id, project_id) REFERENCES projects (organization_id, id), 
    UNIQUE (organization_id, id)
);

CREATE INDEX ix_sprints_organization_id ON sprints (organization_id);

CREATE TABLE identity_documents (
    employee_id VARCHAR(36) NOT NULL, 
    storage_key VARCHAR(300) NOT NULL, 
    media_type VARCHAR(100) NOT NULL, 
    digest VARCHAR(64) NOT NULL, 
    status VARCHAR NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    reviewed_by VARCHAR(36), 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, employee_id) REFERENCES employees (organization_id, id), 
    UNIQUE (storage_key)
);

CREATE INDEX ix_identity_documents_organization_id ON identity_documents (organization_id);

CREATE TABLE leave_requests (
    employee_id VARCHAR(36) NOT NULL, 
    starts_on DATE NOT NULL, 
    ends_on DATE NOT NULL, 
    reason VARCHAR(1000) NOT NULL, 
    status VARCHAR NOT NULL, 
    reviewed_by VARCHAR(36), 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (ends_on >= starts_on), 
    FOREIGN KEY(organization_id, employee_id) REFERENCES employees (organization_id, id)
);

CREATE INDEX ix_leave_requests_organization_id ON leave_requests (organization_id);

CREATE TABLE lifecycle_plans (
    employee_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(30) NOT NULL, 
    snapshot JSON NOT NULL, 
    proposed JSON NOT NULL, 
    proposed_by VARCHAR(36) NOT NULL, 
    approved_by VARCHAR(36), 
    status VARCHAR NOT NULL, 
    history JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, employee_id) REFERENCES employees (organization_id, id)
);

CREATE INDEX ix_lifecycle_plans_organization_id ON lifecycle_plans (organization_id);

CREATE TABLE task_details (
    task_id VARCHAR(36) NOT NULL, 
    priority VARCHAR NOT NULL, 
    deadline TIMESTAMP WITH TIME ZONE, 
    sprint_id VARCHAR(36), 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, sprint_id) REFERENCES sprints (organization_id, id), 
    FOREIGN KEY(organization_id, task_id) REFERENCES tasks (organization_id, id), 
    UNIQUE (task_id)
);

CREATE INDEX ix_task_details_organization_id ON task_details (organization_id);

ALTER TABLE "ai_usage" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "ai_usage" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "ai_usage"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "budgets" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "budgets" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "budgets"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "cloud_assessments" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "cloud_assessments" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "cloud_assessments"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "cost_records" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "cost_records" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "cost_records"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "departments" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "departments" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "departments"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "detection_policies" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "detection_policies" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "detection_policies"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "audit_seals" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "audit_seals" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "audit_seals"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "complaints" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "complaints" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "complaints"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "incident_events" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "incident_events" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "incident_events"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "integration_accounts" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "integration_accounts" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "integration_accounts"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "project_comments" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "project_comments" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "project_comments"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "project_members" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "project_members" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "project_members"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "repository_projects" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "repository_projects" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "repository_projects"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "scan_jobs" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "scan_jobs" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "scan_jobs"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "sprints" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "sprints" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "sprints"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "identity_documents" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "identity_documents" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "identity_documents"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "leave_requests" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "leave_requests" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "leave_requests"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "lifecycle_plans" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "lifecycle_plans" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "lifecycle_plans"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "task_details" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "task_details" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "task_details"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON audit_seals FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE UNIQUE INDEX uq_payroll_org_id ON payroll (organization_id, id);

CREATE TABLE payroll_rules (
    name VARCHAR(100) NOT NULL, 
    version INTEGER NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    components JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (version > 0), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, name, version)
);

CREATE INDEX ix_payroll_rules_organization_id ON payroll_rules (organization_id);

CREATE TABLE payroll_calculations (
    payroll_id VARCHAR(36) NOT NULL, 
    rule_id VARCHAR(36) NOT NULL, 
    base NUMERIC(14, 2) NOT NULL, 
    breakdown JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, payroll_id) REFERENCES payroll (organization_id, id), 
    FOREIGN KEY(organization_id, rule_id) REFERENCES payroll_rules (organization_id, id), 
    UNIQUE (payroll_id)
);

CREATE INDEX ix_payroll_calculations_organization_id ON payroll_calculations (organization_id);

ALTER TABLE "payroll_rules" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "payroll_rules" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "payroll_rules"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

ALTER TABLE "payroll_calculations" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "payroll_calculations" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "payroll_calculations"
                USING (organization_id = nullif(current_setting('mesh.organization_id', true), ''))
                WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id', true), ''));

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON payroll_rules FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

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

-- Running upgrade 0004 -> 0005

ALTER TABLE ai_usage ADD COLUMN model VARCHAR(100);

ALTER TABLE ai_usage ADD COLUMN billing_currency VARCHAR(3);

ALTER TABLE ai_usage ADD COLUMN pricing JSON;

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

-- Running upgrade 0005 -> 0006

CREATE TABLE identity_sessions (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    provider_session_id VARCHAR(36) NOT NULL, 
    client_hint VARCHAR(200) NOT NULL, 
    ip_digest VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    revocation_reason VARCHAR(40), 
    PRIMARY KEY (id), 
    UNIQUE (user_id, provider_session_id)
);

CREATE INDEX ix_identity_sessions_user_id ON identity_sessions (user_id);

ALTER TABLE "identity_sessions" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "identity_sessions" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "identity_sessions"
            USING (user_id = nullif(current_setting('mesh.user_id',true),''))
            WITH CHECK (user_id = nullif(current_setting('mesh.user_id',true),''));

DO $mesh_session_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public.identity_sessions FROM anon;
                END IF;
            END; $mesh_session_grants$;;

DO $mesh_session_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public.identity_sessions FROM authenticated;
                END IF;
            END; $mesh_session_grants$;;

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

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

-- Running upgrade 0007 -> 0008

ALTER TABLE cloud_assessments ADD COLUMN errors JSON;

ALTER TABLE cloud_assessments ADD COLUMN coverage JSON;

ALTER TABLE cloud_assessments ADD COLUMN limitations JSON;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON cloud_assessments FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

UPDATE alembic_version SET version_num='0008' WHERE alembic_version.version_num = '0007';

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

-- Running upgrade 0010 -> 0011

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
    $mesh_retention$;;

REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM PUBLIC;

UPDATE alembic_version SET version_num='0011' WHERE alembic_version.version_num = '0010';

-- Running upgrade 0011 -> 0012

ALTER TABLE employment_changes ADD COLUMN resolution_reason VARCHAR(1000);

ALTER TABLE employment_changes ADD COLUMN resolved_at TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0012' WHERE alembic_version.version_num = '0011';

-- Running upgrade 0012 -> 0013

ALTER TABLE leave_entitlements ADD COLUMN holidays JSON DEFAULT '[]' NOT NULL;

UPDATE alembic_version SET version_num='0013' WHERE alembic_version.version_num = '0012';

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

-- Running upgrade 0014 -> 0015

ALTER TABLE identity_documents ADD COLUMN ocr_status VARCHAR(30) DEFAULT 'not_configured' NOT NULL;

ALTER TABLE identity_documents ADD COLUMN ocr_attempts INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE identity_documents ADD COLUMN ocr_lease_until TIMESTAMP WITH TIME ZONE;

ALTER TABLE identity_documents ADD COLUMN ocr_ciphertext TEXT;

ALTER TABLE identity_documents ADD COLUMN ocr_error_code VARCHAR(60);

ALTER TABLE identity_documents ADD COLUMN ocr_completed_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX ix_identity_ocr_queue ON identity_documents (organization_id, ocr_status, ocr_lease_until);

UPDATE alembic_version SET version_num='0015' WHERE alembic_version.version_num = '0014';

-- Running upgrade 0015 -> 0016

ALTER TABLE security_events ADD COLUMN context JSON DEFAULT '{}' NOT NULL;

CREATE INDEX ix_event_org_category_time ON security_events (organization_id, category, occurred_at, id);

UPDATE alembic_version SET version_num='0016' WHERE alembic_version.version_num = '0015';

-- Running upgrade 0016 -> 0017

CREATE TRIGGER immutable_observation BEFORE UPDATE ON security_events FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_immutable_observation$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                REVOKE UPDATE, DELETE ON TABLE public.security_events FROM mesh_runtime;
            END IF;
        END; $mesh_immutable_observation$;;

CREATE TRIGGER immutable_observation BEFORE UPDATE ON anomalies FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_immutable_observation$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                REVOKE UPDATE, DELETE ON TABLE public.anomalies FROM mesh_runtime;
            END IF;
        END; $mesh_immutable_observation$;;

UPDATE alembic_version SET version_num='0017' WHERE alembic_version.version_num = '0016';

-- Running upgrade 0017 -> 0018

ALTER TABLE cost_records ADD COLUMN request_key VARCHAR(36);

ALTER TABLE cost_records ADD COLUMN request_digest VARCHAR(64);

ALTER TABLE cost_records ADD COLUMN recorded_by VARCHAR(36);

ALTER TABLE cost_records ADD COLUMN billing_provider VARCHAR(10);

ALTER TABLE cost_records ADD COLUMN usage_quantity NUMERIC(20, 6);

ALTER TABLE cost_records ADD COLUMN usage_unit VARCHAR(20);

ALTER TABLE cost_records ADD CONSTRAINT uq_cost_request_key UNIQUE (organization_id, request_key);

ALTER TABLE cost_records ADD CONSTRAINT fk_cost_actor_tenant FOREIGN KEY(organization_id, recorded_by) REFERENCES memberships (organization_id, user_id);

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_receipt_complete CHECK ((request_key IS NULL AND request_digest IS NULL AND recorded_by IS NULL) OR (request_key IS NOT NULL AND request_digest IS NOT NULL AND recorded_by IS NOT NULL));

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_request_key_length CHECK (request_key IS NULL OR length(request_key)=36);

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_digest_length CHECK (request_digest IS NULL OR length(request_digest)=64);

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_usage_pair CHECK ((usage_quantity IS NULL AND usage_unit IS NULL) OR (usage_quantity IS NOT NULL AND usage_unit IS NOT NULL));

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_usage_nonnegative CHECK (usage_quantity IS NULL OR usage_quantity >= 0);

CREATE INDEX ix_cost_org_currency_period ON cost_records (organization_id, currency, period, department);

UPDATE alembic_version SET version_num='0018' WHERE alembic_version.version_num = '0017';

-- Running upgrade 0018 -> 0019

ALTER TABLE memberships ADD COLUMN access_not_before TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0019' WHERE alembic_version.version_num = '0018';

-- Running upgrade 0019 -> 0020

CREATE FUNCTION public.mesh_rehire_clear_project_grants(reviewed_plan text)
    RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog
    AS $mesh_rehire$
    DECLARE
        scoped_org text := nullif(current_setting('mesh.organization_id', true), '');
        scoped_user text := nullif(current_setting('mesh.user_id', true), '');
        target_user text;
        removed integer;
    BEGIN
        IF scoped_org IS NULL OR scoped_user IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.memberships m JOIN public.organizations o ON o.id=m.organization_id
            WHERE m.organization_id=scoped_org AND m.user_id=scoped_user
                AND m.active AND m.role='owner' AND o.status='active'
        ) THEN
            RAISE EXCEPTION 'Active tenant owner required' USING ERRCODE='42501';
        END IF;
        SELECT e.user_id INTO target_user
        FROM public.lifecycle_plans p
        JOIN public.employees e ON e.organization_id=p.organization_id AND e.id=p.employee_id
        JOIN public.memberships m ON m.organization_id=e.organization_id AND m.user_id=e.user_id
        JOIN public.memberships a ON a.organization_id=p.organization_id AND a.user_id=p.approved_by
        WHERE p.id=reviewed_plan AND p.organization_id=scoped_org AND p.kind='rehire'
            AND p.status='reconciliation_required' AND p.proposed_by<>p.approved_by
            AND p.proposed_by<>scoped_user AND a.active AND a.role='owner'
            AND NOT m.active AND m.role NOT IN ('owner','hr')
            AND e.status='offboarded' AND e.verification_status='approved';
        IF target_user IS NULL THEN
            RAISE EXCEPTION 'Independently reviewed inactive rehire required' USING ERRCODE='42501';
        END IF;
        DELETE FROM public.project_members WHERE organization_id=scoped_org AND user_id=target_user;
        GET DIAGNOSTICS removed = ROW_COUNT;
        RETURN removed;
    END
    $mesh_rehire$;
    REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM PUBLIC;
    DO $grant_rehire$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
            GRANT EXECUTE ON FUNCTION public.mesh_rehire_clear_project_grants(text) TO mesh_runtime;
        END IF;
    END $grant_rehire$;;

UPDATE alembic_version SET version_num='0020' WHERE alembic_version.version_num = '0019';

-- Running upgrade 0020 -> 0021

REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM PUBLIC;
        DO $mesh_function_acl$
        DECLARE api_role text;
        BEGIN
            FOR api_role IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
                EXECUTE 'REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM ' || quote_ident(api_role);
                EXECUTE 'REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM ' || quote_ident(api_role);
            END LOOP;
        END $mesh_function_acl$;;

UPDATE alembic_version SET version_num='0021' WHERE alembic_version.version_num = '0020';

-- Running upgrade 0021 -> 0022

ALTER TABLE scan_jobs ADD CONSTRAINT uq_scan_finding_provenance UNIQUE (organization_id, repository_id, id, commit_sha);

ALTER TABLE findings ADD COLUMN "column" INTEGER;

ALTER TABLE findings ADD COLUMN dependency JSON;

ALTER TABLE findings ADD COLUMN scan_job_id VARCHAR(36);

ALTER TABLE findings ADD COLUMN commit_sha VARCHAR(40);

ALTER TABLE findings ADD CONSTRAINT fk_finding_scan_commit FOREIGN KEY(organization_id, repository_id, scan_job_id, commit_sha) REFERENCES scan_jobs (organization_id, repository_id, id, commit_sha);

ALTER TABLE findings ADD CONSTRAINT ck_finding_provenance_pair CHECK ((scan_job_id IS NULL AND commit_sha IS NULL) OR (scan_job_id IS NOT NULL AND commit_sha IS NOT NULL));

ALTER TABLE findings ADD CONSTRAINT ck_finding_commit_length CHECK (commit_sha IS NULL OR length(commit_sha)=40);

ALTER TABLE findings ADD CONSTRAINT ck_finding_column_positive CHECK ("column" IS NULL OR "column">0);

CREATE INDEX ix_finding_org_repository_scan ON findings (organization_id, repository_id, scan_job_id);

UPDATE alembic_version SET version_num='0022' WHERE alembic_version.version_num = '0021';

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

-- Running upgrade 0025 -> 0026

ALTER TABLE cloud_assessments ADD COLUMN normalized_context JSON;

ALTER TABLE cloud_assessments ADD CONSTRAINT ck_cloud_context_envelope CHECK (
        normalized_context IS NULL OR (
          octet_length(normalized_context::text) <= 8388608
          AND COALESCE(json_typeof(normalized_context) = 'object',false)
          AND COALESCE(normalized_context->'envelope'->>'contract' = 'mesh.cloud-context',false)
          AND COALESCE(normalized_context->'envelope'->>'schema_version' = '1.0.0',false)
          AND COALESCE(normalized_context->'envelope'->>'publication_state' = 'sealed',false)
          AND COALESCE(normalized_context->'envelope'->>'organization_id' = organization_id,false)
          AND COALESCE(normalized_context->'envelope'->>'assessment_id' = id,false)
          AND COALESCE(normalized_context->'envelope'->'scope'->>'organization_id' = organization_id,false)
          AND COALESCE(json_typeof(normalized_context->'assets') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'principals') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'permissions') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'relationships') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'evidence') = 'array',false)
        ));

CREATE FUNCTION mesh_guard_cloud_context_job() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public AS $$
      DECLARE job_id text;
      BEGIN
        job_id := NEW.normalized_context->'envelope'->>'source_job_id';
        IF job_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.cloud_assessment_jobs j
          WHERE j.organization_id=NEW.organization_id AND j.id=job_id
            AND j.assessment_id=NEW.id AND j.status='completed'
        ) THEN RAISE EXCEPTION 'Cloud context job linkage is invalid'; END IF;
        RETURN NEW;
      END $$;

CREATE CONSTRAINT TRIGGER cloud_context_job_link
      AFTER INSERT ON cloud_assessments DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION mesh_guard_cloud_context_job();

REVOKE ALL ON FUNCTION mesh_guard_cloud_context_job() FROM PUBLIC;

REVOKE ALL ON TABLE cloud_assessments FROM PUBLIC;

DO $cloud_acl$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON FUNCTION mesh_guard_cloud_context_job() FROM anon;
            REVOKE ALL ON TABLE cloud_assessments FROM anon;
          END IF;
        END $cloud_acl$;

DO $cloud_acl$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON FUNCTION mesh_guard_cloud_context_job() FROM authenticated;
            REVOKE ALL ON TABLE cloud_assessments FROM authenticated;
          END IF;
        END $cloud_acl$;

DO $cloud_acl$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
            REVOKE ALL ON FUNCTION mesh_guard_cloud_context_job() FROM service_role;
            REVOKE ALL ON TABLE cloud_assessments FROM service_role;
          END IF;
        END $cloud_acl$;

DO $cloud_runtime$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
        GRANT SELECT,INSERT ON TABLE cloud_assessments TO mesh_runtime;
        REVOKE UPDATE,DELETE ON TABLE cloud_assessments FROM mesh_runtime;
      END IF;
    END $cloud_runtime$;

UPDATE alembic_version SET version_num='0026' WHERE alembic_version.version_num = '0025';

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

-- Running upgrade 0027 -> 0028

ALTER TABLE identity_documents ADD CONSTRAINT uq_identity_document_tenant_id UNIQUE (organization_id, id);

CREATE TABLE document_holds (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    document_id VARCHAR(36) NOT NULL, 
    request_key VARCHAR(36) NOT NULL, 
    reason_code VARCHAR(30) NOT NULL, 
    placed_by VARCHAR(36) NOT NULL, 
    released_at TIMESTAMP WITH TIME ZONE, 
    released_by VARCHAR(36), 
    release_reason VARCHAR(30), 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, document_id) REFERENCES identity_documents (organization_id, id), 
    FOREIGN KEY(organization_id, placed_by) REFERENCES memberships (organization_id, user_id), 
    FOREIGN KEY(organization_id, released_by) REFERENCES memberships (organization_id, user_id), 
    CONSTRAINT uq_document_hold_request UNIQUE (organization_id, request_key), 
    CONSTRAINT ck_document_hold_request CHECK (length(request_key)=36), 
    CONSTRAINT ck_document_hold_reason CHECK (reason_code IN ('dispute','investigation','regulatory','other')), 
    CONSTRAINT ck_document_hold_release CHECK ((released_at IS NULL AND released_by IS NULL AND release_reason IS NULL) OR (released_at IS NOT NULL AND released_by IS NOT NULL AND released_by != placed_by AND released_at >= created_at AND release_reason IS NOT NULL AND release_reason IN ('resolved','entered_in_error','other')))
);

CREATE INDEX ix_document_holds_organization_id ON document_holds (organization_id);

CREATE INDEX ix_document_hold_active ON document_holds (organization_id, document_id, released_at);

CREATE UNIQUE INDEX uq_document_active_hold ON document_holds (organization_id, document_id) WHERE released_at IS NULL;

ALTER TABLE "document_holds" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "document_holds" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "document_holds"
        USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
        WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE FUNCTION mesh_guard_document_hold() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public AS $$
      DECLARE document_status text;
      BEGIN
        IF TG_OP='INSERT' THEN
          SELECT status INTO document_status FROM public.identity_documents
            WHERE organization_id=NEW.organization_id AND id=NEW.document_id FOR UPDATE;
          IF document_status IS NULL OR document_status='deleted' OR NEW.released_at IS NOT NULL THEN
            RAISE EXCEPTION 'Hold requires a retained document and active admission';
          END IF;
          IF EXISTS (SELECT 1 FROM public.document_holds WHERE organization_id=NEW.organization_id
            AND document_id=NEW.document_id AND released_at IS NULL) THEN
            RAISE EXCEPTION 'Document already has an active hold';
          END IF;
          RETURN NEW;
        END IF;
        IF OLD.released_at IS NOT NULL OR NEW.released_at IS NULL OR
          ROW(NEW.id,NEW.organization_id,NEW.created_at,NEW.document_id,NEW.request_key,NEW.reason_code,NEW.placed_by)
          IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.created_at,OLD.document_id,OLD.request_key,OLD.reason_code,OLD.placed_by)
        THEN RAISE EXCEPTION 'Hold evidence is immutable except one independent release'; END IF;
        RETURN NEW;
      END $$;

CREATE FUNCTION mesh_guard_held_document() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public AS $$
      BEGIN
        IF EXISTS (SELECT 1 FROM public.document_holds WHERE organization_id=OLD.organization_id
          AND document_id=OLD.id AND released_at IS NULL) THEN
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Held document cannot be deleted'; END IF;
          IF ROW(NEW.id,NEW.organization_id,NEW.employee_id,NEW.storage_key,NEW.media_type,NEW.digest,NEW.expires_at,NEW.ocr_ciphertext)
            IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.employee_id,OLD.storage_key,OLD.media_type,OLD.digest,OLD.expires_at,OLD.ocr_ciphertext)
            OR NEW.status='deleted' THEN RAISE EXCEPTION 'Held document preservation is immutable'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END $$;

CREATE TRIGGER document_hold_guard BEFORE INSERT OR UPDATE ON document_holds FOR EACH ROW EXECUTE FUNCTION mesh_guard_document_hold();

CREATE TRIGGER no_document_hold_delete BEFORE DELETE ON document_holds FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER held_document_guard BEFORE UPDATE OR DELETE ON identity_documents FOR EACH ROW EXECUTE FUNCTION mesh_guard_held_document();

REVOKE ALL ON TABLE document_holds FROM PUBLIC;

REVOKE ALL ON FUNCTION mesh_guard_document_hold() FROM PUBLIC;

REVOKE ALL ON FUNCTION mesh_guard_held_document() FROM PUBLIC;

DO $hold_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON TABLE document_holds FROM anon;
            REVOKE ALL ON FUNCTION mesh_guard_document_hold(),mesh_guard_held_document() FROM anon;
          END IF;
        END $hold_acl$;

DO $hold_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON TABLE document_holds FROM authenticated;
            REVOKE ALL ON FUNCTION mesh_guard_document_hold(),mesh_guard_held_document() FROM authenticated;
          END IF;
        END $hold_acl$;

DO $hold_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
            REVOKE ALL ON TABLE document_holds FROM service_role;
            REVOKE ALL ON FUNCTION mesh_guard_document_hold(),mesh_guard_held_document() FROM service_role;
          END IF;
        END $hold_acl$;

DO $hold_runtime$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON TABLE document_holds TO mesh_runtime;
        REVOKE DELETE ON TABLE document_holds FROM mesh_runtime;
      END IF;
    END $hold_runtime$;

UPDATE alembic_version SET version_num='0028' WHERE alembic_version.version_num = '0027';

-- Running upgrade 0028 -> 0029

CREATE INDEX ix_memberships_user_org ON memberships (user_id, organization_id);

CREATE POLICY self_membership_discovery ON memberships FOR SELECT
            USING (
                nullif(current_setting('mesh.organization_id', true), '') IS NULL
                AND user_id = nullif(current_setting('mesh.user_id', true), '')
                AND active
            );

UPDATE alembic_version SET version_num='0029' WHERE alembic_version.version_num = '0028';

COMMIT;

