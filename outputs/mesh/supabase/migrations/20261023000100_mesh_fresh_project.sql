
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


-- Additional Supabase hardening: browser roles never receive application table access.
REVOKE ALL ON TABLE public.alembic_version FROM anon, authenticated;
REVOKE ALL ON TABLE public."ai_usage" FROM anon, authenticated;
REVOKE ALL ON TABLE public."anomalies" FROM anon, authenticated;
REVOKE ALL ON TABLE public."audit_logs" FROM anon, authenticated;
REVOKE ALL ON TABLE public."audit_seals" FROM anon, authenticated;
REVOKE ALL ON TABLE public."budgets" FROM anon, authenticated;
REVOKE ALL ON TABLE public."cloud_assessments" FROM anon, authenticated;
REVOKE ALL ON TABLE public."complaints" FROM anon, authenticated;
REVOKE ALL ON TABLE public."cost_records" FROM anon, authenticated;
REVOKE ALL ON TABLE public."deliveries" FROM anon, authenticated;
REVOKE ALL ON TABLE public."departments" FROM anon, authenticated;
REVOKE ALL ON TABLE public."detection_policies" FROM anon, authenticated;
REVOKE ALL ON TABLE public."domain_challenges" FROM anon, authenticated;
REVOKE ALL ON TABLE public."employees" FROM anon, authenticated;
REVOKE ALL ON TABLE public."findings" FROM anon, authenticated;
REVOKE ALL ON TABLE public."identity_documents" FROM anon, authenticated;
REVOKE ALL ON TABLE public."incident_events" FROM anon, authenticated;
REVOKE ALL ON TABLE public."incidents" FROM anon, authenticated;
REVOKE ALL ON TABLE public."integration_accounts" FROM anon, authenticated;
REVOKE ALL ON TABLE public."invitations" FROM anon, authenticated;
REVOKE ALL ON TABLE public."leave_requests" FROM anon, authenticated;
REVOKE ALL ON TABLE public."lifecycle_plans" FROM anon, authenticated;
REVOKE ALL ON TABLE public."memberships" FROM anon, authenticated;
REVOKE ALL ON TABLE public."organizations" FROM anon, authenticated;
REVOKE ALL ON TABLE public."outbox" FROM anon, authenticated;
REVOKE ALL ON TABLE public."payroll" FROM anon, authenticated;
REVOKE ALL ON TABLE public."payroll_calculations" FROM anon, authenticated;
REVOKE ALL ON TABLE public."payroll_rules" FROM anon, authenticated;
REVOKE ALL ON TABLE public."project_comments" FROM anon, authenticated;
REVOKE ALL ON TABLE public."project_members" FROM anon, authenticated;
REVOKE ALL ON TABLE public."projects" FROM anon, authenticated;
REVOKE ALL ON TABLE public."repositories" FROM anon, authenticated;
REVOKE ALL ON TABLE public."repository_projects" FROM anon, authenticated;
REVOKE ALL ON TABLE public."response_actions" FROM anon, authenticated;
REVOKE ALL ON TABLE public."scan_jobs" FROM anon, authenticated;
REVOKE ALL ON TABLE public."security_events" FROM anon, authenticated;
REVOKE ALL ON TABLE public."sprints" FROM anon, authenticated;
REVOKE ALL ON TABLE public."task_details" FROM anon, authenticated;
REVOKE ALL ON TABLE public."tasks" FROM anon, authenticated;
REVOKE ALL ON TABLE public."trust_events" FROM anon, authenticated;
-- Run as Supabase database administrator, separately from application Alembic migrations.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('mesh-identity', 'mesh-identity', false, 2097152, ARRAY['image/png','image/jpeg'])
ON CONFLICT (id) DO UPDATE SET public=false, file_size_limit=2097152,
allowed_mime_types=ARRAY['image/png','image/jpeg'];

-- Restrictive policies override accidental permissive policies for this bucket.
-- No direct client access: HR authorization happens in the backend before 60-second signing.
-- Replace only MESH-owned policies atomically, so this script is safe to reapply.
DO $mesh_storage_policies$
BEGIN
DROP POLICY IF EXISTS mesh_identity_no_client_read ON storage.objects;
DROP POLICY IF EXISTS mesh_identity_no_client_insert ON storage.objects;
DROP POLICY IF EXISTS mesh_identity_no_client_update ON storage.objects;
DROP POLICY IF EXISTS mesh_identity_no_client_delete ON storage.objects;
CREATE POLICY mesh_identity_no_client_read ON storage.objects AS RESTRICTIVE
FOR SELECT TO anon, authenticated USING (bucket_id <> 'mesh-identity');
CREATE POLICY mesh_identity_no_client_insert ON storage.objects AS RESTRICTIVE
FOR INSERT TO anon, authenticated WITH CHECK (bucket_id <> 'mesh-identity');
CREATE POLICY mesh_identity_no_client_update ON storage.objects AS RESTRICTIVE
FOR UPDATE TO anon, authenticated USING (bucket_id <> 'mesh-identity')
WITH CHECK (bucket_id <> 'mesh-identity');
CREATE POLICY mesh_identity_no_client_delete ON storage.objects AS RESTRICTIVE
FOR DELETE TO anon, authenticated USING (bucket_id <> 'mesh-identity');
END;
$mesh_storage_policies$;
