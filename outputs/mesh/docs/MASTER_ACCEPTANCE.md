# Master backend acceptance evidence

This maps section 41 of the original MESH request to concrete evidence. Local implementation, authorized external-service acceptance and production readiness are separate. No frontend is included.

| Original criterion | Implemented evidence | Limits / remaining acceptance |
|---|---|---|
| Core API services | Current OpenAPI and API_REFERENCE.md; HR, DevTrack, VADER, finance and AI routes | Remaining scope and operational review are listed in IMPLEMENTATION_STATUS.md |
| Database migrations | Alembic 0022, 20 frozen SQL artifacts; fresh PostgreSQL apply and dump/restore; hosted schema verifier | Supabase CLI migration history has not been reconciled; do not replay bootstrap |
| Authentication and RBAC | JWT/session/MFA adapters, deny-by-default permissions, provider and authorization tests | Real inbox/CAPTCHA/provider administration and organization-specific policies remain unverified |
| Tenant isolation | Forced RLS on 51 tables; restricted runtime role; real PostgreSQL and hosted cross-tenant tests | Independent security review remains required |
| HR and project workflows | Automated workflow suites and 20 hosted rollback-only checks | Local reviewed provisioning/rehire/restoration work is implemented; live provider and organization-policy acceptance remain pending |
| Isolated security scanning | Actual Semgrep/Bandit/Gitleaks/OSV fixture and containment evidence in scanner reports | Real GitHub App checkout/webhook acceptance needs authorized configuration; image advisory gates fail |
| Synthetic VADER ingestion/correlation | Deterministic bounded event ingestion, idempotency, anomaly/correlation/simulator tests | Synthetic detection does not validate field accuracy or broad real telemetry connectors |
| Explainable deterministic risk | Versioned policies, eight dimensions, coverage bounds and immutable snapshots | Missing evidence stays unknown; scores are advisory |
| Configured AI or local alternative | Actual local Ollama inference, validated schema and usage/quota/outage gates; Redis/ASGI streaming tests | Tiny local fixture model is not a quality benchmark; ambiguous vendor-charge reconciliation remains pending |
| Background workers | Durable outbox, scan/cloud/OCR/retention workers; leases, retries, fencing and status | Docker results must match the current source fingerprint; production worker configuration remains required |
| API documentation | Current OpenAPI, API reference, authentication/RBAC and frontend integration guide | No frontend has been created or connected |
| Reproducible local deployment | Source Dockerfiles, pinned dependencies, Compose and disposable VM acceptance | Check current fingerprint in docker-runtime-results.json; production deployment is separate |
| Critical automated tests | Windows, actual PostgreSQL, hosted rollback and Linux reports | Skipped opt-in cases and per-report limitations remain explicit; counts overlap |
| Frontend integration guide | FRONTEND_INTEGRATION_GUIDE.md and typed contracts, including finance request-key retries | Integration is deferred until separately supplied and authorized |

Production clearance is false. OS advisory matches, independent review, deployment validation, operational monitoring, privacy/retention decisions and production recovery acceptance remain material work. Passing the local criteria above must not be presented as independent production security approval. Future statutory payroll, legal calendars or semantic vulnerability identity tracking must not silently replace the actual original acceptance criteria.
