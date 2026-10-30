# API reference

Generated from current FastAPI. Backend only. Tenant APIs require bearer authentication and X-Organization-ID; provider/account exceptions are described in AUTHENTICATION.md.

| Method | Path | Operation |
|---|---|---|
| POST | `/api/v1/auth/register` | Register |
| POST | `/api/v1/auth/verify` | Verify Email |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/refresh` | Refresh |
| POST | `/api/v1/auth/recover` | Recover |
| POST | `/api/v1/auth/resend` | Resend Signup |
| POST | `/api/v1/auth/logout` | Logout |
| POST | `/api/v1/organizations` | Create Organization |
| GET | `/api/v1/organizations/current` | Current Organization |
| POST | `/api/v1/organizations/domain-challenges` | Domain Start |
| POST | `/api/v1/organizations/domain-challenges/{challenge_id}/verify` | Domain Verify |
| POST | `/api/v1/invitations` | Create Invitation |
| POST | `/api/v1/invitations/accept` | Accept |
| DELETE | `/api/v1/invitations/{invitation_id}` | Cancel Invitation |
| POST | `/api/v1/invitations/{invitation_id}/resend` | Resend Invitation |
| POST | `/api/v1/employees` | Create Employee |
| GET | `/api/v1/employees` | Employees |
| GET | `/api/v1/employees/{employee_id}` | Employee |
| POST | `/api/v1/hr/payroll` | Payroll |
| GET | `/api/v1/hr/payroll` | Payroll Records |
| POST | `/api/v1/projects` | Project Create |
| GET | `/api/v1/projects` | Projects |
| GET | `/api/v1/projects/{project_id}` | Project Get |
| POST | `/api/v1/projects/{project_id}/decision` | Project Decision |
| POST | `/api/v1/tasks` | Task Create |
| GET | `/api/v1/repositories/{repository_id}` | Repository Get |
| GET | `/api/v1/findings/{finding_id}` | Finding Get |
| PATCH | `/api/v1/findings/{finding_id}` | Finding Decide |
| POST | `/api/v1/vader/events` | Event Ingest |
| GET | `/api/v1/vader/events` | Events |
| GET | `/api/v1/vader/events/{event_id}` | Event Get |
| GET | `/api/v1/vader/anomalies` | Anomalies |
| GET | `/api/v1/vader/incidents` | Incidents |
| GET | `/api/v1/vader/incidents/{incident_id}` | Incident Get |
| PATCH | `/api/v1/vader/incidents/{incident_id}` | Incident Update |
| GET | `/api/v1/vader/incidents/{incident_id}/graph` | Incident Graph |
| POST | `/api/v1/vader/simulator/{run_id}` | Simulation |
| POST | `/api/v1/vader/responses` | Response Propose |
| POST | `/api/v1/vader/responses/{response_id}/approve` | Response Approve |
| POST | `/api/v1/trust/events` | Trust Event |
| GET | `/api/v1/trust/{user_id}` | Trust Score |
| GET | `/api/v1/ai/incidents/{incident_id}` | Incident Summary |
| GET | `/api/v1/audit` | Audit List |
| GET | `/api/v1/users/me` | User Profile |
| GET | `/api/v1/finance/budgets` | Budgets |
| POST | `/api/v1/finance/budgets` | Budget Create |
| GET | `/api/v1/finance/budgets/{budget_id}/variance` | Budget Variance |
| GET | `/api/v1/audit/integrity` | Audit Integrity |
| GET | `/api/v1/jobs` | Jobs |
| GET | `/api/v1/jobs/{job_id}` | Job Get |
| POST | `/api/v1/jobs/{job_id}/retry` | Retry Job |
| POST | `/api/v1/hr/departments` | Department Create |
| GET | `/api/v1/hr/departments` | Departments |
| POST | `/api/v1/hr/leave` | Leave Create |
| GET | `/api/v1/hr/leave` | Leaves |
| POST | `/api/v1/hr/leave/{leave_id}/decision` | Leave Decide |
| POST | `/api/v1/hr/complaints` | Complaint Create |
| GET | `/api/v1/hr/complaints` | Complaints |
| POST | `/api/v1/hr/lifecycle` | Lifecycle Propose |
| GET | `/api/v1/hr/lifecycle/{plan_id}` | Lifecycle Get |
| POST | `/api/v1/hr/lifecycle/{plan_id}/decision` | Lifecycle Approve |
| POST | `/api/v1/hr/lifecycle/{plan_id}/execute` | Lifecycle Execute |
| POST | `/api/v1/finance/costs` | Cost Create |
| GET | `/api/v1/finance/costs` | Costs |
| GET | `/api/v1/finance/budget-variance` | Budget Variance History |
| GET | `/api/v1/finance/usage` | Infrastructure Usage |
| GET | `/api/v1/finance/summary` | Finance Summary |
| GET | `/api/v1/finance/what-if` | Finance What If |
| POST | `/api/v1/projects/{project_id}/members` | Project Member Add |
| POST | `/api/v1/projects/{project_id}/sprints` | Sprint Create |
| GET | `/api/v1/projects/{project_id}/sprints` | Sprints |
| POST | `/api/v1/projects/{project_id}/comments` | Comment Create |
| GET | `/api/v1/projects/{project_id}/comments` | Comments |
| GET | `/api/v1/projects/{project_id}/tasks` | Tasks |
| PATCH | `/api/v1/tasks/{task_id}` | Task Update |
| POST | `/api/v1/repositories` | Repository Add |
| POST | `/api/v1/repositories/{repository_id}/revoke` | Repository Revoke |
| POST | `/api/v1/scans` | Scan Request |
| GET | `/api/v1/scans/{job_id}` | Scan Status |
| GET | `/api/v1/scans/{job_id}/events` | Scan Events |
| POST | `/api/v1/scans/{job_id}/cancel` | Scan Cancel |
| GET | `/api/v1/repositories/{repository_id}/scans` | Repository Scans |
| GET | `/api/v1/repositories/{repository_id}/remediation` | Repository Remediation |
| GET | `/api/v1/findings/{finding_id}/history` | Finding History |
| GET | `/api/v1/repositories/{repository_id}/findings` | Findings |
| GET | `/api/v1/repositories/{repository_id}/analytics` | Repository Analytics |
| GET | `/api/v1/repositories/{repository_id}/finding-identities` | Finding Identities |
| POST | `/api/v1/repositories/{repository_id}/finding-identities/index` | Finding Identities Index |
| GET | `/api/v1/finding-identities/{identity_id}/observations` | Finding Identity Observations |
| POST | `/api/v1/employees/{employee_id}/identity-documents` | Upload |
| GET | `/api/v1/hr/identity-documents/{document_id}/signed-url` | Signed Url |
| POST | `/api/v1/hr/identity-documents/{document_id}/decision` | Review |
| GET | `/api/v1/hr/identity-documents/{document_id}/ocr` | Ocr Result |
| POST | `/api/v1/hr/identity-documents/{document_id}/ocr/retry` | Retry Ocr |
| POST | `/api/v1/hr/identity-documents/{document_id}/ocr/manual-review` | Manual Ocr |
| POST | `/api/v1/hr/identity-documents/expire` | Expire Documents |
| PUT | `/api/v1/vader/detection-policy` | Policy Set |
| GET | `/api/v1/vader/baseline/{actor_id}` | Baseline |
| GET | `/api/v1/vader/risk/{incident_id}` | Risk |
| POST | `/api/v1/vader/cloud/assess` | Cloud Assess |
| GET | `/api/v1/vader/incidents/{incident_id}/risk-evidence` | Risk Evidence |
| GET | `/api/v1/vader/cloud/assessments` | Cloud History |
| GET | `/api/v1/vader/cloud/assessments/{assessment_id}` | Cloud Assessment Get |
| GET | `/api/v1/ai/owner` | Owner Ai |
| GET | `/api/v1/ai/hr` | Hr Ai |
| GET | `/api/v1/ai/projects/{project_id}` | Project Ai |
| GET | `/api/v1/ai/vader/{incident_id}` | Vader Ai |
| GET | `/api/v1/ai/risk-assessments/{assessment_id}` | Risk Ai |
| GET | `/api/v1/ai/usage` | Ai Usage |
| PUT | `/api/v1/auth/password` | Update Password |
| PATCH | `/api/v1/organizations/current/status` | Organization Status |
| POST | `/api/v1/hr/payroll-rules` | Rule Create |
| GET | `/api/v1/hr/payroll-rules` | Rules |
| POST | `/api/v1/hr/payroll/compute` | Compute |
| POST | `/api/v1/hr/lifecycle/{plan_id}/compensation` | Lifecycle Compensation |
| POST | `/api/v1/hr/lifecycle/{plan_id}/rehire-activation` | Rehire Activation |
| POST | `/api/v1/hr/lifecycle/{plan_id}/restore-scim` | Rehire Restore Scim |
| POST | `/api/v1/hr/lifecycle/{plan_id}/abort-rehire` | Rehire Abort |
| POST | `/api/v1/hr/lifecycle/{plan_id}/provision-reconcile` | Provision Reconcile |
| POST | `/api/v1/hr/lifecycle/{plan_id}/activate-provisioned-scim` | Provision Activate |
| POST | `/api/v1/hr/lifecycle/{plan_id}/cancel-provisioning` | Provision Cancel |
| POST | `/api/v1/hr/lifecycle/{plan_id}/cancel` | Lifecycle Cancel |
| PATCH | `/api/v1/hr/complaints/{complaint_id}` | Complaint Update |
| POST | `/api/v1/hr/lifecycle/{plan_id}/reconcile` | Reconcile |
| PATCH | `/api/v1/sprints/{sprint_id}` | Sprint Update |
| GET | `/api/v1/tasks/{task_id}/details` | Task Details |
| POST | `/api/v1/hr/employees/{employee_id}/scim-account` | Scim Link |
| POST | `/api/v1/hr/job-roles` | Job Role Create |
| GET | `/api/v1/hr/job-roles` | Job Roles |
| POST | `/api/v1/hr/employment-changes` | Employment Propose |
| GET | `/api/v1/hr/employment-changes` | Employment Changes |
| POST | `/api/v1/hr/employment-changes/{change_id}/decision` | Employment Decide |
| POST | `/api/v1/hr/employment-changes/{change_id}/apply` | Employment Apply |
| POST | `/api/v1/hr/employment-changes/{change_id}/withdraw` | Employment Withdraw |
| GET | `/api/v1/hr/employees/{employee_id}/employment-terms` | Employment History |
| PUT | `/api/v1/hr/employees/{employee_id}/leave-allowance/{year}` | Allowance Set |
| GET | `/api/v1/hr/employees/{employee_id}/leave-allowance/{year}` | Allowance Get |
| POST | `/api/v1/hr/leave/{leave_id}/cancel` | Leave Cancel |
| POST | `/api/v1/vader/incidents/{incident_id}/notes` | Note Create |
| GET | `/api/v1/vader/incidents/{incident_id}/notes` | Notes |
| GET | `/api/v1/users/me/sessions` | Sessions |
| DELETE | `/api/v1/users/me/sessions/{session_id}` | Revoke Session |
| POST | `/api/v1/users/me/sessions/revoke-others` | Revoke Others |
| POST | `/api/v1/webhooks/github` | Github Webhook |
| PUT | `/api/v1/devtrack/approval-policy` | Policy Set |
| GET | `/api/v1/devtrack/approval-policy` | Policy Get |
| GET | `/api/v1/devtrack/review-queue` | Review Queue |
| POST | `/api/v1/projects/{project_id}/reviews` | Review Add |
| GET | `/api/v1/projects/{project_id}/reviews` | Reviews |
| GET | `/api/v1/projects/{project_id}/activity` | Activity |
| POST | `/api/v1/vader/risk-policies` | Policy Create |
| GET | `/api/v1/vader/risk-policies` | Policies |
| POST | `/api/v1/vader/risk-assessments` | Assess |
| GET | `/api/v1/vader/risk-assessments` | History |
| GET | `/api/v1/vader/risk-assessments/{assessment_id}` | Assessment Get |
| GET | `/api/v1/vader/risk-summary` | Summary |
| POST | `/api/v1/vader/cloud/jobs` | Request Assessment |
| GET | `/api/v1/vader/cloud/jobs` | Jobs |
| GET | `/api/v1/vader/cloud/jobs/{job_id}` | Job Status |
| POST | `/api/v1/vader/cloud/jobs/{job_id}/cancel` | Cancel |
| POST | `/api/v1/vader/cloud/jobs/{job_id}/retry` | Retry |
| GET | `/api/v1/auth/mfa/factors` | Factor List |
| POST | `/api/v1/auth/mfa/enroll` | Enroll |
| POST | `/api/v1/auth/mfa/factors/{factor_id}/challenge` | Challenge |
| POST | `/api/v1/auth/mfa/factors/{factor_id}/verify` | Verify |
| DELETE | `/api/v1/auth/mfa/factors/{factor_id}` | Unenroll |
| POST | `/api/v1/ai/stream` | Stream |
| GET | `/api/v1/ai/usage/summary` | Usage Summary |
| GET | `/api/v1/ai/requests` | Requests |
| GET | `/api/v1/ai/requests/{request_id}` | Detail |
| POST | `/api/v1/ai/requests/{request_id}/cancel-expired` | Cancel Expired |
| POST | `/api/v1/ai/requests/{request_id}/reconcile` | Reconcile |
| GET | `/api/v1/vader/correlation-policy` | Policy Get |
| PUT | `/api/v1/vader/correlation-policy` | Policy Put |
| GET | `/api/v1/vader/correlation-policies` | Policy History |
| GET | `/health/live` | Live |
| GET | `/health/ready` | Ready |

Complete schemas: [OpenAPI](docs/openapi.json). New contracts: [Private OCR](docs/PRIVATE_OCR.md), [AI streaming](docs/AI_STREAMING.md), [Finding lifecycle](docs/FINDING_LIFECYCLE.md), [Lifecycle compensation](docs/LIFECYCLE_COMPENSATION.md), [Risk](docs/RISK_ENGINE.md), [Finance](docs/FINANCE.md), [Rehire](docs/REHIRE.md), [Provisioning](docs/SCIM_PROVISIONING.md), [Finding provenance](docs/FINDING_PROVENANCE.md), [Finding identities](docs/FINDING_IDENTITIES.md), [AI accounting](docs/AI_ACCOUNTING.md), [Error contract](docs/ERROR_CONTRACT.md), [Business concurrency](docs/BUSINESS_CONCURRENCY.md), [Artifact integrity](docs/ARTIFACT_INTEGRITY.md), [Correlation policy](docs/CORRELATION_POLICY.md), [VADER read audit](docs/VADER_READ_AUDIT.md), [Worker health](docs/WORKER_HEALTH.md).


## 30 October backend additions

- GET /api/v1/invitations: authorized tenant-scoped, filtered/paginated invitation metadata.
- GET /api/v1/invitations/{invitation_id}/delivery: latest queue state, sanitized transport outcome and attempts; never proof of inbox receipt. See docs/INVITATION_DELIVERY.md.
- GET /api/v1/ai/owner?currency=USD and POST /api/v1/ai/stream currency selection: explicit currency separation, sole-currency auto-selection,409 for ambiguous recorded currencies. See docs/AI_CURRENCY.md.

Canonical OpenAPI is docs/openapi.json (191operations/164paths). Existing v1 clients remain supported; new optional output/request fields are additive.


## Self-organization discovery

GET /api/v1/users/me/organizations: authenticated-self cursor-paginated organization metadata without an organization header. No additional access is granted. See docs/MEMBERSHIP_DISCOVERY.md. OpenAPI192operations/165paths.
