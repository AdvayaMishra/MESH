# Continuation plan

Historical starting plan. Current deployed revision, verified scope and remaining work are maintained in IMPLEMENTATION_STATUS.md; this document does not describe the current migration head.

Preserve the 0001 migration and existing tested API behavior. Add 0002 for new tables/indexes; do not regenerate 0001.

1. HR leave/complaints/departments, deterministic finance, approved employee lifecycle plans with local revocation first and external reconciliation.
2. Project membership, sprints/comments/task transitions, repository-to-project grants, authorized scan jobs and finding updates.
3. Dedicated Docker scanner launcher with immutable commit checkout; network-free resource-constrained Semgrep/Bandit/Gitleaks; OSV queries transmit package metadata only. Never mount the Docker socket into the API.
4. Private document pipeline (magic bytes, malware gate, private Supabase Storage, HR-only signed links, retention) with explicit integration credentials.
5. VADER configurable detection, baseline/cold start, incident state management, read-only AWS assessment adapters and fixtures; no real response enforcement.
6. Provider-independent structured AI adapters, minimized context, authorization and usage records; encrypted durable invitation delivery; audit hash chaining.
7. Incremental migration, PostgreSQL RLS integration suite, storage deny policies, Compose/CI checks, tests, OpenAPI and updated status. Docker/PostgreSQL are absent from this host; runtime claims require actual evidence.
