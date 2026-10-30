# Test report — 27 October 2026

Results are from this execution environment, not a production environment. Offline store suites use minimal test-only React and Zustand shims under Node 24; they do not validate real React rendering, persistence middleware or browser behavior.

| Command | Result |
| --- | --- |
| `npm run verify:hr` | Passed: 143 checks, with test shims. |
| `npm run verify:data:offline` | Passed: 212 checks, with test shims. |
| `bash scripts/run-verify.sh verify-security-workflows` | Passed: 15 checks, with test shims. |
| `bash scripts/run-verify.sh verify-repository-workflows` | Passed: 15 checks, with test shims. |
| `bash scripts/run-verify.sh verify-sprints` | Passed: 12 checks, with test shims. |
| `bash scripts/run-verify.sh verify-review-workflows` | Passed: 12 checks, with test shims. |
| `bash scripts/run-verify.sh verify-task-workflows` | Passed, with test shims; includes creation, permission, duplicate, deletion and tenant checks. |
| `node tests/what-if.test.mjs` | Passed: 8 checks. |
| `node tests/api-client.test.mjs` | Passed: 7 checks. |
| `node scripts/audit-source.mjs` | Passed: 156 source files, 58 routes and 779 local imports. This checks static import existence only. |
| `npm ci --offline` | Failed: `ENOTCACHED` for zustand; package cache incomplete. |
| `npm ci --ignore-scripts --no-audit --no-fund` | Attempted, stalled and stopped; npm registry access is restricted here. |
| `npm run typecheck`, `npm run lint`, `npm run build` | Could not run: `tsc`, `eslint` and `next` unavailable without installed dependencies. |
| `npm run dev`, `npm run test:e2e` | Could not start: `next` and `playwright` unavailable. Browser testing and user journeys were not performed. |

No production build, TypeScript validation, complete lint, application startup or end-to-end test has passed here. Re-run all checks after installing dependencies and Playwright browsers. The independent Node tests require Node 24's TypeScript stripping; the verification script uses the project compiler when available and otherwise Node 24 plus shims.
