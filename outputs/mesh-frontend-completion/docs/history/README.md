# MESH frontend

MESH is a multi-module enterprise SaaS frontend demo built with Next.js, React, TypeScript and Zustand. The Owner, People, DevTrack and VADER modules use seeded simulated organizations. This is unfinished software, not a production release; the backend is not connected.

## Setup

Install a compatible Node.js runtime (Node 20.9 or newer; Node 24 supports the independent tests below) and npm, then run:

```sh
npm ci
npm run dev
```

Open http://localhost:3000. The demo provides role and organization switching; its identity checks, emails, GitHub, security actions and AI are simulations. Client-side permissions and session state are not security controls. Do not enter real confidential data.

```sh
npm run verify:hr
npm run verify:data:offline
bash scripts/run-verify.sh verify-security-workflows
bash scripts/run-verify.sh verify-task-workflows
bash scripts/run-verify.sh verify-sprints
bash scripts/run-verify.sh verify-review-workflows
bash scripts/run-verify.sh verify-repository-workflows
npm run audit:source
npm run typecheck
npm run lint
npm run build
npm run test:e2e
node tests/what-if.test.mjs
node tests/api-client.test.mjs
```

Playwright requires a browser installation (for example `npx playwright install chromium`). The independent Node tests require Node 24's built-in TypeScript stripping. See FRONTEND_TEST_REPORT.md for actual results in this environment and BACKEND_INTEGRATION_GUIDE.md before connecting real data.
