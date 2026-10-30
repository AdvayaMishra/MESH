# MESH frontend — PROGRESS (checkpoint 4 — NOT a final release)

> Sandbox note: `npm ci` crashed partway ("Exit handler never called", network disabled; `react`, `zustand`, `next`, `@types/*` absent).
> TypeScript/ESLint/Next build/Playwright could NOT be run. UI pages (.tsx) are therefore UNCOMPILED and UNTESTED in a browser.
> The pure logic + store layer was verified by script (see FRONTEND_TEST_REPORT.md).

## Completed in checkpoint 4 (F2 People/HR) — logic verified, UI unverified
- **Complaints**: seeds for both tenants (`lib/api/mock/hr-seed.ts`); store actions submit / status transition / resolve / withdraw /
  assign / escalate-to-Restricted / message + internal note; all re-check access via `viewKind()` (`stores/workspace-store.ts`).
  UI: `/workspace/complaints` (all roles, own cases only, complainant-visible events), `/people/complaints` (HR queue + detail drawer;
  Restricted cases redacted for non-assigned HR; Owner blocked by route rule and by `viewKind`).
- **Promotions**: seeds both tenants; create (HR/Owner only, validated), approve/reject (proposer != approver, never self, reason required to reject),
  withdraw. UI `/people/promotions` (new rule: owner+hr). Approval records a decision only; no salary/role/access change.
  **Regression fixed**: grade ladders only knew E/S/G, so Northwind bands (`N`, `N-S`, `N-G`) could never be promoted.
- **Leave**: `lib/leave.ts` (weekday count, date/overlap/medical-note validation), store submit / cancel / decide (HR or Owner, never self,
  reason required to decline). UI `/workspace/leave` (all roles) and review on `/people/payroll` (buttons shown only if permitted).
- **Employees**: directory search/filter/profile pre-existed. Profile now reads leave and promotions from the live store slice.
  Tenant switch: `RouteGuard` remounts on `${orgId}:${role}`; HR state is a per-tenant slice (verified: no cross-tenant leakage).
- Nav: People → Complaints, Promotions; Workspace → My complaints, My leave. People overview "Pending complaints" no longer hardcoded 2
  (HR sees real open count; Owner sees promotions-in-review instead and no complaint data).
- Test tooling: `scripts/verify-hr.ts`, `scripts/run-verify.sh` (tsc emit + node, with TEST-ONLY shims for zustand/react in `scripts/shims/`),
  `e2e/hr-workflows.spec.ts` (written, NOT run).

## Partially completed / not done
- Browser behavior of all new pages (dialogs, toasts, focus) unverified. Likely compile risks: prop names on `Field`/`Dialog`/`Button` variants were
  copied from existing usage but not type-checked; `EmptyState` has no icon prop (already removed).
- Leave: no balances/accrual (by design). Leave review UI exists only on Payroll page (no dedicated HR leave inbox).
- Complaints: no attachments, no assignee picker (assign-to-me only), no notifications to reporter (status is visible in My complaints).
- Promotions: no Draft state UI, no editing after submission.
- Dev "Send message"/"Export" on directory remain simulated toasts (labelled simulated).

## Known bugs / risks
- `PROGRESS` claims about 196 checks are for `verify-tenants`; verify-hr has 143 checks. Neither covers rendering.
- Dates use the browser's real clock for validation; seeds are fixed to Oct 2026 (demo "today" 2026-10-27).
- All HR state resets on reload (in-memory zustand, per tenant slice).
- Frontend permissions are UX only; backend must enforce complaint visibility tiers and tenant isolation (RLS).

## Remaining (F2 close-out, then not started)
Run the full toolchain with network, fix compile/lint errors, run Playwright, then F3+ only after that.

## ChatGPT takeover — incremental change (27 October 2026)
- Added dedicated `/people/leave/review` inbox with pending/all filters, employee request details, note entry, permission-aware approve/decline, and self-approval prohibition.
- Added People navigation link to leave approvals.
- Ran existing offline HR logic verification: **143 passed, 0 failed**.
- `npm ci` exceeded the execution timeout in this environment; complete TypeScript/build/Playwright checks remain **unverified**. Do not present this as a finished frontend or production integration.
