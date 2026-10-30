# Bounded business concurrency regression

`test_live_concurrent_business_requests_do_not_leak_tenant_or_role_context` executes 96 ASGI requests at concurrency four against the actual API and disposable PostgreSQL with a restricted, non-superuser, non-bypass-RLS role. It creates two synthetic tenants with distinct HR, owner and security-analyst memberships.

Each repeated set checks authorized HR directory reads, finding reads and finance summaries; role-denied employee reads; nonmember tenant denial; and cross-tenant repository denial. Returned employee/finding identifiers must belong to the selected tenant. All 96 request IDs must be unique. A fresh database session must have no residual tenant context and see no employees without explicitly selecting a tenant.

Sessions commit the synthetic read audits and close on each request; errors roll back. Five-second statement and three-second lock timeouts bound database work. The fixture uses four request threads over independent sessions and the normal application authentication/authorization dependencies after the identity boundary.

Identity-provider verification is deliberately replaced with fixed synthetic test identities. This check does not exercise JWT verification, Supabase, Redis throttling or a real network server. It does not establish authenticated production throughput, endurance, capacity or percentile latency. Real Auth/MFA and loopback HTTP checks have separate reports. The synthetic database is removed with the disposable native cluster or owned Compose project.

Run with the existing PostgreSQL integration suite and a generated database whose name begins `mesh_test_`. Never point the suite at hosted or real data. Native PostgreSQL and Linux/Compose acceptance execute this case independently; their test totals overlap.
