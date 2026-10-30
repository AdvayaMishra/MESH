# Final frontend and existing backend integration

## 29 October 2026 — Supabase network blocker resolved

The user requested fixing the network restriction and granted turn-scoped network access. Restarted only the owned local API/Redis runtime. Actual API liveness and readiness now both return200; readiness checks the configured database runtime role, reads the organizations table and pings authenticated Redis. The final frontend login and its proxied backend readiness were checked separately (see ../mesh/docs/final-integration-network-recheck.json). No test authentication substitutions, migrations, hosted business writes or provider changes were made. This resolves the prior Windows10013 connectivity blocker for the current runtime; full live hosted frontend user journeys remain a separate acceptance step. The grant is scoped to this turn, so future sessions may need network permission again.

29 October 2026. Canonical frontend: `outputs/mesh-frontend-completion`. Canonical backend: `outputs/mesh`. The former connected preview remains a reference. The user authorized integrating the final frontend and opening the project in VS Code. This document supersedes earlier frontend notes saying the final frontend has no backend connection.

## Open and run in VS Code

Open `MESH.code-workspace` at the workspace root. It contains Backend, Final Frontend and Connected Preview Reference folders. The code is edited in those existing directories. Tasks available under Terminal > Run Task:

- MESH: build final frontend
- MESH: run final frontend
- MESH: run backend and Redis
- MESH: test connected workflows

The final frontend uses port3120 and `.next-connected`; the actual backend uses port8000 with password-protected loopback Redis on6388. Test servers use3100/8011 and are separate. The owned backend launcher is `outputs/mesh/infrastructure/local/run_backend.py`; its stop marker is `work/final-integration-runtime/stop`. No Docker socket or privileged provider key is passed to the browser. Running another backend launcher is refused while its ownership ledger exists.

## Connected workflows

| Area | Integrated behavior |
|---|---|
| Authentication | Actual backend signup/login, owner-name contract, numeric OTP verification, confirmation resend, recovery/password change, logout, genuine Turnstile callback tokens, expired/error/consumed token invalidation. |
| Sessions | Same-origin backend-for-frontend, bounded HttpOnly/SameSite cookies, server-side refresh-token use, one shared refresh for denied reads, no automatic business-write retries, session/MFA screens and an organization-independent authenticator step-up page. |
| Organizations | Create an organization after confirmation, restore a saved organization selection, verified self-profile/role, actual DNS and website proof, invitations/resend/revoke, acceptance from email token links. Invitation tokens are removed from the address bar and are not persisted in browser storage. |
| Projects | Native final project lists/proposal form, independent senior reviews and owner decisions, project comments, organization-account membership/manager assignment, versioned approval policy. Unsupported proposal budget/schedule fields are removed in connected mode. |
| Tasks and sprints | Native board, real task creation for authorized senior managers, assignee account references, persisted status transitions, manager-only priority/deadline/sprint edits, actual task-detail reads and sprint creation. Startup metadata reads are bounded; selected task details load separately. |
| HR | Actual directory/export, employee and department creation, job-role/compensation-band definitions, employment proposals/independent review/application, allowance updates preserving configured holidays, leave requests/review and lifecycle proposal/owner approval/HR execution. |
| Payroll | Manual payroll records, versioned fixed/percentage rule editor, actual computation and saved record display; no transfer of funds. |
| Documents | Private JPEG/PNG upload capped at2MiB, HR review, OCR-result/retry/hold controls from existing services; configured screening/engine/provider readiness still governs acceptance. |
| Finance | Recorded costs and budgets, selected-currency separation, recorded budget variance, AWS collection job/report controls and real what-if calculation and honest unavailable forecasts/history. |
| Repository security | Existing GitHub installation/repository setup, immutable scan requests/status polling, findings and dispositions. Real provider/worker configuration remains required. |
| VADER | Actual accessible events/anomalies/incidents, investigation notes/status/graphs, independently approved response simulations, risk policies/assessments and explicitly synthetic scenarios; no invented live monitoring or risk reduction. |
| Cloud | Saved assessments/job status and explicit AWS deferral/coverage limitations. |
| AI | Owner/HR/project/incident insights, bounded cancellable authenticated SSE, request-accounting records and explicit provider/usage limitations. |
| Shared | Actual audit records, reviewed Trust Stars lookup/evidence-backed event recording, role-aware native shell/search, explicit demo mode and unavailable-service states. |

Owner approval/finance authority does not grant task management or private HR access. Senior developers manage their authorized projects/tasks. Junior developers can propose projects and progress their own assigned tasks. HR handles private employee/payroll/document data; lifecycle approval belongs to the owner, and employment changes require independent HR review. Security analysts consume their authorized security/repository evidence. Backend authorization and tenant filtering remain authoritative.

Use `npm run sync:backend` to synchronize the allowlist and OpenAPI snapshot after exporting the backend contract; `npm run test:connected` runs the connected acceptance suite.

The reviewed transport allowlist and frontend OpenAPI snapshot match the existing189-operation contract. External webhooks should target the backend directly with provider signatures; the browser proxy is not an external connector deployment.

## Existing backend limits shown honestly

General notification delivery/read state, combined activity feeds, scheduled report generation, support/ticket transmission, pull-request merge/review operations, task comments/deletion/reassignment and unsupported task text/story-point/label edits have no corresponding supported backend workflow in this snapshot. Their demo mutations cannot execute in connected mode. Existing deadlines/sprint assignments cannot be cleared through the current task API. Organization selection uses a saved UUID or manual selection because this backend exposes no cross-membership organization-discovery API. Private records and company-wide totals are not inferred from a self-profile.

AWS credentials, an authorized real SCIM directory, production OCR/privacy/image clearance, public HTTPS deployment and the friend's unmerged workstreams remain separate requirements. No credentials, paid provider, actual employee document or production deployment was fabricated by this integration.

## Verification and runtime limits

Machine results are in `verification/` and backend `docs/final-integration-*.json`. Browser acceptance uses actual HTTP requests to the real FastAPI routers and an isolated SQLite database. The portable test fixture is `connected-tests/backend-fixture.py`. Only identity-provider verification and challenge transport are explicitly substituted in the fixture. These tests verify persistence/authorization behavior, not live Supabase PostgreSQL RLS or real CAPTCHA; separate earlier reports contain those scoped live checks. Test-mode substitutions are absent from the actual port8000 launcher.

The actual API's liveness and local authenticated Redis pass. Hosted readiness currently fails because this Codex session denies the outgoing database socket with Windows10013. The configured Supabase pooler credentials and readable verify-full CA are retained. No new approval request was sent, as requested. Live hosted frontend journeys remain unverified in this session until network access is authorized and the owned backend is restarted. TLS verification has not been weakened and no synthetic fallback replaces the actual runtime.

No source was uploaded to GitHub, no archive was created and no existing migration was changed.


### Final verification checkpoint

- Production build and TypeScript: passed.
- ESLint:0errors,6warnings (unused declarations, compiler/library opt-outs and the inherited demo navigation warning).
- Node regression:11passed.
- Connected browser regression:22passed,0failed/skipped/flaky; includes35routes across all five roles.
- Backend regression:1,280passed,32skipped,0failures/errors.
- Known configured backend secret boundary:8unique values checked against318source/browser-bundle files;0matches. This is a scoped check, not a comprehensive security audit.
- Hosted runtime: API live200; ready503, outgoing database socket denied (Windows10013). Hosted end-to-end acceptance remains pending.

Exact results and current-source hashes are saved in verification/final-integration-summary.json and verification/final-integration-source-hashes.json. Previous verification files describe their original demo or earlier connected checkpoints and are not substituted for this final22-test result.


## 30 October backend continuation

Contract/bridge allowlist synchronized to191operations/164paths. Owner insight requests now auto-select a sole recorded currency; ?currency=USD is available and multiple currencies require explicit selection. Invitation list/delivery APIs are implemented and documented in backend docs/INVITATION_DELIVERY.md; the existing manual invitation UI has not yet been replaced with list/status controls. Production build/types pass after contract synchronization; prior22browser acceptance results remain historical. New full backend regression1303passed/32skipped. Runtime readiness200 and new bridge routes correctly require authentication. See backend docs/backend-continued-results.json.


## 30 October self-membership discovery backend

New authenticated GET /api/v1/users/me/organizations and synchronized bridge allowlist bring the contract to192operations/165paths. Migration0029is deployed with57forced-RLS tables preserved. Future frontend selection can consume items/next_cursor; the current welcome UI has NOT been modified to use it. See backend docs/MEMBERSHIP_DISCOVERY.md and membership-discovery-results.json.
