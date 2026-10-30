# MESH implementation plan

Repository inspection: empty workspace, no application, frontend, Git checkout, or existing instructions found. Python 3.12 is available through the bundled runtime. Docker and PostgreSQL executables were not found on PATH. No Supabase tools are connected.

1. Foundation: FastAPI modular monolith, SQLAlchemy, Alembic, PostgreSQL RLS, configuration, Compose, readiness, tests.
2. Identity: Supabase JWT verification and provider adapter; membership-derived tenant context, deny-by-default RBAC, invitation lifecycle. Domain proof and private documents require separate hardening before activation.
3. Enterprise: deterministic payroll and finance, restricted employee records, project approval and task workflows, reviewed Trust Stars ledger.
4. DevTrack: repository authorization, findings and scan contracts. Untrusted-code execution remains disabled until an isolated scanner runtime is validated.
5. VADER: typed event ingestion, deduplication, deterministic detection, temporal actor correlation, explainable risk, synthetic simulator, approved simulated response.
6. AI: authorization-aware minimized context, validated local deterministic summaries; external provider remains opt-in.
7. Hardening: tenant/security regression tests, migration validation where runtime permits, CI, API export, truthful status and frontend integration documentation.

Each phase is a milestone, not permission to weaken earlier security boundaries. Missing external systems must fail closed. Deliver the executable local subset and explicitly list every deferred requirement in IMPLEMENTATION_STATUS.md.
