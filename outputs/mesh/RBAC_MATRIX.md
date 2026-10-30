# Permission matrix

The executable source is `backend/app/auth.py::PERMISSIONS`. Unlisted permission/role combinations are denied.

| Role | Granted operations |
|---|---|
| Owner | Manage organization/domain/status, invite HR, assign project managers, read tenant projects and approve/reject reviewed proposals, finance read/write/budgets/analytics, lifecycle approval/manual reconciliation, audit read/integrity, review Trust Stars |
| HR | Read/write employee directory/departments, invite employees, independently review leave/complaints/identity documents, payroll rules/calculation, lifecycle proposal/execution, review Trust Stars |
| Senior Developer | Create/read authorized projects, review proposals, manage assigned projects/tasks/sprints, read project-authorized repositories/findings and queue scans |
| Junior Developer | Create/read authorized proposals/projects, comments, assigned task progress up to review; cannot approve own completion |
| Security Analyst | Read tenant repositories/findings and queue scans, ingest/read telemetry/incidents, tune detection policy, perform read-only cloud assessment, propose/independently approve simulated responses, read audit |

Owner has no HR identity-document or other employees' complaint access and no raw payroll write permission. Complaint authors may read their own reports. Analysts cannot approve their own response; developers cannot review their own proposals. Owner/HR do not receive Trust Stars. Project membership and repository-to-project grants enforce resource-level access. Senior review permits review of another tenant proposal without granting its general project read endpoint until membership is assigned. Privileged roles require verified aal2 when REQUIRE_PRIVILEGED_MFA is enabled, and production requires that setting.
