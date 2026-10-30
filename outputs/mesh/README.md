# MESH backend

Current checkpoint: Supabase 0025/55 forced-RLS tables; private OCR, reviewed rehire/restoration, lifecycle compensation, finding history and AI/scan SSE implemented. Windows 759/23 skipped; current runtime acceptance passes. OS gates fail and remaining master requirements are documented in IMPLEMENTATION_STATUS.md. Backend only.





























Continued modular FastAPI backend implementation. **The complete master-prompt acceptance criteria are not yet met; this is not production-ready.** No frontend was created, modified or integrated.

Implemented workflows now include tenant/resource authorization, invitations and dual domain proof, HR leave/complaints/private-ID review/lifecycle, versioned deterministic payroll, finance budgets/forecasting, DevTrack membership/sprints/tasks/comments, durable scan jobs and isolated Docker scanner source, VADER detection/correlation/incident workflows, read-only AWS assessment and structured AI adapters.

```sh
python -m venv .venv
# Activate .venv for your shell
python -m pip install -r requirements-dev.lock -e .
pytest -q
```

Copy .env.example to .env and follow LOCAL_DEVELOPMENT.md plus docs/INTEGRATION_CONFIGURATION.md. Docker Compose supplies development service configuration. Hosted Supabase PostgreSQL is deployed and verified. Temporary native Redis, Mailpit, signed-definition ClamAV and a separate worker process passed live checks. The actual core-only Docker scanner passes all three tools and containment in the approved disposable VM. Compose startup, API/worker restrictions, dump/restore and the Linux/PostgreSQL suite now pass. Base OS/native-library assessment remains pending; the two historical full-CLI Python dependency advisories are excluded from the current scanner image; see docs/PHASE_1_3_STATUS.md. Hosted Auth/MFA/private Storage acceptance is recorded in docs/supabase-provider-results.json.

Read IMPLEMENTATION_STATUS.md for exact implemented/partial/pending distinctions and docs/VERIFICATION.md for observed results. API_REFERENCE.md and docs/openapi.json describe actual APIs. FRONTEND_INTEGRATION_GUIDE.md documents the future connection contract without creating frontend code. See docs/SCANNING.md before enabling the dedicated privileged scanner launcher.
