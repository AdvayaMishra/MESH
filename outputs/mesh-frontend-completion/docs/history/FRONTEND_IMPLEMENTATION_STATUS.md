# Frontend implementation status

**Incomplete demo; not production-ready.** This review is based on source inspection and the limited checks listed in FRONTEND_TEST_REPORT.md, not a complete browser audit. The supplied project contains 57 route files and a tenant-scoped mock workspace. The following summarizes visible implementation, not a claim that every control or user journey has been verified.

| Area | Status |
| --- | --- |
| Owner | Dashboard, finance, project filtering and CSV exports exist; preset What-If scenarios and a percentage-based forecast calculator are simulated. Full administration, budgets and cross-page consistency require review. |
| People | Directory, leave, promotions and confidential complaint workflows and role checks exist in source; end-to-end enforcement and all HR actions remain unverified. |
| DevTrack | Project/task views, filtering, task editing, sprint fields and simulated PR merge exist; complete task, sprint, scanning and GitHub workflows remain unverified. |
| VADER | Incident search, response approvals/reversals and rule-based Copilot exist in demo source. Security operations and scans are not real. Complete incident and remediation journeys require verification. |
| Shared | Demo role navigation, tenant switching, search, notifications, reports and settings exist. Authentication, tenant isolation and access control are client-side demonstrations, not security boundaries. |
| Integration | Typed dataset and opt-in request transport exist. No live adapter or endpoints are configured. Backend authorization, persistence and validation remain to be implemented. |

## Changes made in this delivery

- Added a deterministic free-text demo calculation for percentage increases/decreases in forecast cloud spend, with explicit assumptions and unsupported-query guidance. Existing preset scenarios remain.
- Implemented audit CSV download for the selected module/result filters. Table text search does not change the exported rows, and the UI states this.
- Reset What-If and Copilot sessions on organization changes; cancel delayed Copilot responses when its session unmounts.
- Added an unconnected typed HTTP boundary with bearer-token and organization context, plus independent tests.
- Improved the offline verification script's missing-compiler error and updated the documentation.

Many actions elsewhere still use component-local state or simulated toasts; a complete button-by-button audit has not been completed. Previous checkpoint claims are historical and have not been revalidated here.

## Continued work — 27 October 2026

- The shared async data hook now reloads on organization change and hides results from the previous tenant while loading; the existing dashboard route guard also remounts tenant/role subtrees. Browser verification is still needed.
- Employee directory and audit CSV downloads now include all records matching both the search and dropdown filters, across pages. Directory messaging explicitly says it is unavailable rather than claiming to draft a message.
- Finding assignments update the workspace, survive navigation/tenant switching during the session, and are recorded in the simulated audit log. Finding and incident changes and response approval/reversal check demo roles and validate targets. Resolved incidents cannot be changed in the current demo.
- Task creation checks the demo role, active project, assignee, fields and duplicate identifiers; new identifiers are collision-resistant. A confirmation dialog deletes tasks for owner/senior developer roles, except tasks linked to pull requests. These changes affect simulated state only.
- HR, tenant, security and task logic checks run without installed npm dependencies on Node 24 using test-only React/Zustand shims. They are not a substitute for testing against real libraries or a browser.

## Continued work — sprint planning and reviews

- Added an organization-scoped demo sprint planner: create named sprints with validated dates, start one at a time, complete active sprints, and calculate completed task points at completion. Task create/edit forms select sprints and project timelines read the active organization's sprint state. Sprint state survives demo tenant switching in memory. There is no backend persistence.
- Corrected a project timeline crash caused by hardcoded sprint names from another tenant.
- ID review decisions now validate role, self-review, pending status and resubmission notes; history and notes remain in the tenant's workspace state. The UI explicitly says no email is sent.
- Project proposals use collision-resistant IDs and validate actor and fields. Owner decisions validate role, status and rejection notes, record history and no longer claim actual funds or notifications were sent.
- DevTrack dashboard uses the active demo identity and current workspace pull requests rather than impersonating the senior developer or using a hardcoded organization summary.

These changes have logic-only tests and source-import checks; UI rendering, accessibility and end-to-end behavior are not verified. Sprint planning is organization-wide and intentionally does not implement a separate per-project sprint or server synchronization.

## Continued work — pull requests, repository authorization and reporting

- Added simulated pull-request approval and change-request decisions with per-PR notes, reviewer history, role/assigned-reviewer checks, self-review prevention and audit entries. Merge remains simulated and requires approval and passing seeded checks. GitHub is not contacted.
- Repository scan authorization is now shared in organization-scoped demo state, is owner-controlled and is used by the scan dialog and security views. Corrected scan messaging: the demo never clones a repository, runs a scanner or creates/deletes files. Organization name/domain editing is shown as backend-dependent rather than falsely reporting a save. Cloud ticket creation is marked unavailable.
- Fixed an existing duplicate `incidents` declaration in VADER overview that would block compilation. The overview and Copilot read current demo incident state; the vulnerability count reads current finding state.
- Report options and export actions now check module-level demo role permissions before displaying/exporting records. This is a client-side UX check, not backend data security.

These features remain session-only demonstrations. UI, build, real dependencies and security enforcement have not been verified in a browser or against a backend.
