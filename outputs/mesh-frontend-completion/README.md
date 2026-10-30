# MESH frontend

## 29 October 2026 — Supabase network blocker resolved

The user requested fixing the network restriction and granted turn-scoped network access. Restarted only the owned local API/Redis runtime. Actual API liveness and readiness now both return200; readiness checks the configured database runtime role, reads the organizations table and pings authenticated Redis. The final frontend login and its proxied backend readiness were checked separately (see ../mesh/docs/final-integration-network-recheck.json). No test authentication substitutions, migrations, hosted business writes or provider changes were made. This resolves the prior Windows10013 connectivity blocker for the current runtime; full live hosted frontend user journeys remain a separate acceptance step. The grant is scoped to this turn, so future sessions may need network permission again.

> Current connected checkpoint —29October2026: final frontend integration is implemented and locally verified. Default mode uses existing backend APIs; the older demo-only descriptions and test counts below are historical. Build/types pass, lint0errors/6warnings,11Node tests and22connected browser tests pass; backend regression1,280passed/32skipped. Live hosted acceptance is blocked by this session's outgoing database socket restriction (Windows10013), not missing Supabase configuration. See [the current integration guide](docs/FINAL_BACKEND_INTEGRATION.md) and [machine results](verification/final-integration-summary.json). Unsupported/missing backend capabilities remain explicitly unavailable.

Enterprise demonstration frontend for OWNER, PEOPLE, DEVTRACK and VADER, completed from the supplied `mesh-frontend-continued-3.zip` while preserving its design system.

## Run the connected version

Open the root MESH.code-workspace in VS Code. Use Terminal > Run Task for the backend/Redis and final frontend tasks; build first after source changes. The final app is http://127.0.0.1:3120/login and the backend is http://127.0.0.1:8000. Keep backend secrets in its private environment file. The current session's hosted database connection needs network permission before real hosted logins/data can work. Select explicit demo mode only to inspect fictional data.

## Historical demo instructions

Requires Node.js 24+, npm and Google Chrome for the configured browser tests.

```powershell
npm ci
npm run build
npm start -- --hostname 127.0.0.1 --port 3001
```

Open `http://127.0.0.1:3001/login`. Use the account menu for the five demo roles and the organization menu for Lumen/Northwind. Business edits survive client-side navigation, role changes and tenant switching within the session. Full reload resets in-memory business data; only role/tenant selection uses browser-tab session storage. No credential or uploaded ID is persisted by this demo.

## Verify

```powershell
npm test
npm run test:logic
npm run audit:source
npm run typecheck
npm run lint
npm run build
npm run test:e2e
# Or run all seven gates and record their actual exit codes:
npm run verify:release
```

The release runner uses actual installed React/Zustand, checks unchanged source fingerprints and starts a bounded loopback browser-test server. Historical shim-based scripts are retained for reference and are not release evidence.

## Capabilities and integration

Organization/employee administration, department budgets, project decisions/allocation, task CRUD and sprints, PR review/merge simulation, scan/finding workflows, ID review/activation, independent lifecycle and payroll review, leave/promotions/private complaints, incident investigation and response reversal, cloud remediation, grounded free-text assistants, role-scoped search/notifications/audit and CSV/XLSX/print-PDF exports and profile/photo/preferences are implemented as demo workflows. Reports support actual CSV and OOXML Excel downloads, record-date filters where timestamps are supplied, and a local printable view with browser Save as PDF.

Authentication, domain checks, scans, cloud/provider actions, payments, email and hosted AI require the separate backend. No real repository, cloud access or payment is changed by this UI. Frontend role controls are a demo UX, not a security boundary. The earlier backend-connected preview remains separate and has not been overwritten.

- [Completion matrix](FRONTEND_COMPLETION_MATRIX.md)
- [Implementation status](FRONTEND_IMPLEMENTATION_STATUS.md)
- [Test report](FRONTEND_TEST_REPORT.md)
- [Backend integration guide](BACKEND_INTEGRATION_GUIDE.md)

Prior supplied reports are preserved under `docs/history/`. Generated dependencies, build caches, credentials and browser traces are excluded from the ZIP.
