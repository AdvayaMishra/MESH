# MESH frontend — implementation checklist

Legend: [x] done & verified · [~] partial · [ ] not started

## Phase 1 — Audit (done)
Baseline (unmodified upload): `npm install` OK **without** `--legacy-peer-deps`; `tsc` clean; `eslint` 0 errors / 4 warnings
(React Compiler `incompatible-library` for react-hook-form `watch` ×3 and TanStack `useReactTable`); `next build` OK, 48 routes.
Runtime crawl (Chromium, 50 URLs): no JS errors; no horizontal page overflow at 390px; 404s only for the not-yet-built routes.

Defects found by audit:
1. `/workspace` crumb link 404s (no `/workspace` page) → console 404 on all 6 workspace routes.
2. No route guard; role is non-persistent client state (reload => Owner). `hiddenForRole` references non-existent route.
3. 37 files import `lib/mock-data` directly; only 6 use `lib/api`. Violates "UI independent of data access".
4. Trust model is 0–5 stars with ±0.1 deltas seeded 3.5–5 for everyone; spec = 0–50 pts, start 20, 1 star / 10 pts, eligible roles only.
5. Role switch does not change identity (always "Alex Morgan").
6. Org switcher is a toast stub; sidebar hardcodes `ORG`.
7. Command palette: pages/people(first 12 only)/projects/incidents; no tasks/issues/findings; no role or tenant filtering; no highlighting.
8. What-If: `db.whatIfScenarios[prompt] ?? null` — only exact preset strings work.
9. Complaints / promotions: only a KPI tile.
10. No automated tests, no Playwright config.
11. Captcha is a placeholder (labelled as such already).

## Phase 2 — Missing functionality
- [~] C. Route permissions + guard + access-denied + persisted demo role
- [ ] A. Complaints workflow
- [ ] B. Promotions workflow
- [ ] D. Global search (tasks, issues, findings, role-aware, grouped, highlight)
- [ ] E. Organization switcher + per-org datasets
- [ ] F. What-If Studio free-text
- [ ] G. VADER copilot free-text
- [ ] Trust score model (0–50)

## Phase 3 — Module completion / data-layer refactor
- [ ] Route all data through `lib/api` (repository pattern, mock adapter + http adapter stub)
- [ ] Dead-control sweep per module
## Phase 4 — Responsive/a11y pass
## Phase 5 — Playwright suite
## Phase 6 — Docs + ZIP
