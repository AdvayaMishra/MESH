# VADER investigation read hardening

Event list/detail, anomaly list, incident list/detail/graph and correlation-policy current/history reads recheck active tenant membership and security-read authority after acquiring the tenant lock. This closes the cached-principal gap when a role or membership is revoked before the guarded operation proceeds. Ingestion and correlation-policy writes similarly refresh security-ingest authority. Other application authorization surfaces are not implicitly certified by this change.

Anomaly lists, incident lists, incident details and incident graphs now append explicit scoped read audits. Event and policy reads retain their own read audits. Missing or foreign incident IDs still return 404 after authorized scope selection. Request logs/errors retain the existing sanitized contract; no raw event payload is inserted into the new read audit records.

Nine focused regression cases exercise successful audited reads, graph policy provenance, foreign-tenant denial and eight stale-principal read surfaces. Correlation tests separately cover stale write/ingestion authority, optimistic versions, relationship modes, thresholds, overflow and retained historical decisions. PostgreSQL tests check append-only policy/snapshot enforcement and cross-tenant foreign keys. Hosted verifier fixtures are synthetic and rolled back.

This does not add a separate failure-audit pipeline, production alert routing or external audit anchoring. Database administrators retain their documented ability to defeat local controls.
