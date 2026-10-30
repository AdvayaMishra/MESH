# MESH frontend — static audit (checkpoint 2 export)

Method: source inspection only (grep/read). The export sandbox had **no network**, so `npm install` failed (ENOTFOUND registry.npmjs.org).
**typecheck, lint, build and Playwright were NOT run in this session.** Historical results in PROGRESS.md remain unverified.

## Implemented (found in source)
- 49 routes under app/ (auth, marketing, owner, people, devtrack, vader, workspace).
- Central permissions (`lib/permissions.ts`), RouteGuard, role-aware sidebar/command palette.
- Data layer: `lib/api/{dataset,index,use-dataset}.ts`, mock adapter `lib/api/mock/lumen.ts`.
  Zero direct `mock-data` imports outside `lib/api` (grep-verified) — the 37-import refactor is complete.
- Tenant store (`stores/tenant-store.ts`, sessionStorage-persisted) + per-org workspace snapshots.
- Trust model 0–50, start 20, eligibility by role+department (`lib/trust.ts`, `hooks/use-trust.ts`, `trust-panel.tsx`).
- Pure rules/types: `lib/complaints.ts`, `lib/promotions.ts`.
- Tests: `e2e/route-guard.spec.ts` (6 test() blocks; parameterised to ~70 cases per PROGRESS), desktop Chromium only.
- No `@ts-ignore` / `any` usage (2 grep hits are comments).

## Changed in this export
- FIXED: `TrustStars` rendered partial/fractional stars and `starsFromScore` returned fractional values (e.g. 3.1).
  Now whole stars only: `floor(points/10)`, clamped 0–50. Fractional helper removed (it was unused).
  Not re-typechecked — change is small and self-contained.

## Partially implemented
- Organization switching: store + UI wired, but only ONE synthetic org (`lumen`) exists → data isolation unproven.
- Complaints / promotions: types and pure rules only. No routes, store state, seeds, or UI.
- Trust events: recording logic exists; history/reason UI not confirmed.

## Missing
- Second synthetic tenant; per-tenant seeds for people/projects/tasks/incidents/finance/notifications/audit.
- Complaint & promotion workflows (employee submit/track route, HR inbox/detail, proposal/approval).
- Global search over all categories (currently limited, per brief).
- Free-text What-If Studio and VADER Copilot (still predefined prompts).
- Versioned mock persistence + documented demo reset.
- Role-specific identity (signed-in user is still a single hardcoded person).
- Dead-control audit: 35 `toast.success/info` call sites exist in components/app; none individually verified as state-mutating.
- Responsive/a11y pass, mobile Chromium + other browsers, expanded Playwright suite.
- BACKEND_INTEGRATION_GUIDE.md, FRONTEND_IMPLEMENTATION_STATUS.md, FRONTEND_TEST_REPORT.md.

## Broken / known risk
- Unknown: current build/lint/test state (see above). First action next session: `npm install && npm run typecheck && npm run lint && npm run build && npm run test:e2e`.
