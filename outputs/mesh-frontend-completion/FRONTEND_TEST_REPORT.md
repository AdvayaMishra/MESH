# Frontend test report

> Current connected checkpoint —29October2026: final frontend integration is implemented and locally verified. Default mode uses existing backend APIs; the older demo-only descriptions and test counts below are historical. Build/types pass, lint0errors/6warnings,11Node tests and22connected browser tests pass; backend regression1,280passed/32skipped. Live hosted acceptance is blocked by this session's outgoing database socket restriction (Windows10013), not missing Supabase configuration. See [the current integration guide](docs/FINAL_BACKEND_INTEGRATION.md) and [machine results](verification/final-integration-summary.json). Unsupported/missing backend capabilities remain explicitly unavailable.

Run completed: 2026-10-28T15:54:35.374Z. Runtime: v24.22.1. Production build, actual React/Zustand dependencies and installed Google Chrome were used. No hosted Supabase business data or external cloud/provider action was used in these tests.

| Gate | Exit code | Time (seconds) |
|---|---:|---:|
| unit | 0 | 0 |
| logic | 0 | 3 |
| source | 0 | 0 |
| types | 0 | 9 |
| lint | 0 | 19 |
| build | 0 | 26 |
| browser | 0 | 158 |

Browser result: **167 passed, 0 failed, 0 skipped, 0 flaky**. Lint: 9 problems (0 errors, 9 warnings).

## Coverage and limits

Role/tenant isolation, restricted complaint views, employee creation, budgets and organization identity, profile isolation/photos, lifecycle independent approval/execution/reversal, payroll review and independent approval, ID submission/review/activation, task creation/edit/comment/deletion, investigation notes and response reversal, cloud remediation/reopening, free-text planning/Copilot, CSV/XLSX downloads and a generated printable PDF, report date filters, every non-dynamic route and representative dynamic routes were exercised. Module layouts were checked at 390, 768 and 1440 pixels and screenshots were captured.

Logic suites use installed React and Zustand, not the historical test shims. They cover HR state machines, review independence, source-tenant ownership, repository/PR workflows, sprints, tasks, assistant grounding, privacy, resource allocation, budgets and payroll. Unit tests cover the planning model and HTTP boundary, including redirects and organization changes during an asynchronous request.

No test proves live external integration, production authentication/security, real OCR/scanner execution, provider billing or payment. Browser viewport checks and visual review are not a complete assistive-technology certification. Seeded historical charts remain labeled demonstrations; unknown commit metrics are not manufactured.

## Evidence

`verification/results.json` records actual gate exits. `verification/browser-summary.json` records final browser counts. Full logs and screenshots remain in the working directory; generated caches, trace archives, dependencies and logs are excluded from the deliverable ZIP.

Source fingerprint before/after the unchanged-source run: `0e9d99676c2e77990e1946466b1feb4f180403b6a211824dc77b3c8beb3e0045`.

The actual browser-downloaded Excel workbook and a formula-safety fixture were independently reopened with openpyxl; ZIP checksums/XML and text cell types passed. The generated browser PDF was parsed with pypdf and its title/demo provenance verified. CSV headers were checked against the advertised report. See `verification/report-format-validation.json`.
