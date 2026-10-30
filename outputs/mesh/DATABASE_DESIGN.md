# Environment variables

| Variable | Purpose |
|---|---|
| DATABASE_URL | SQLAlchemy PostgreSQL DSN; runtime must be non-owner/non-BYPASSRLS |
| POSTGRES_ADMIN_PASSWORD | Compose migration administrator only |
| MESH_DB_PASSWORD | Random 24+ character URL-safe runtime role secret |
| SUPABASE_URL | HTTPS provider base URL, issuer derived as /auth/v1 |
| SUPABASE_ANON_KEY | Auth API anon key; no service-role key required |
| JWT_AUDIENCE | Expected access token audience; default authenticated |
| REDIS_URL | Private shared rate limiter |
| CORS_ORIGINS | JSON array of exact allowed browser origins |
| ENVIRONMENT | development or production; production forbids test mode |
| TEST_MODE | false outside automated tests; permits isolated SQLite fixtures and bypasses rate limiter only |
| MAX_REQUEST_BYTES | Default 262144-byte body cap |
| SMTP_HOST, SMTP_PORT, SMTP_FROM | SMTP transport; production also requires authenticated STARTTLS |
| INVITATION_BASE_URL | Future frontend acceptance URL; token delivered only by email |
| WORKER_ORGANIZATION_ID | Explicit authorized tenant for Compose worker profile |

Additional implemented configuration: MAIL_ENCRYPTION_KEY; SMTP_STARTTLS/USERNAME/PASSWORD; REQUIRE_PRIVILEGED_MFA; SUPABASE_STORAGE_KEY; CLAMAV_HOST/PORT; GITHUB_APP_ID/PRIVATE_KEY/INSTALLATIONS; SCANNER_IMAGE; DOCKER_EXECUTABLE (absolute trusted path); AI_PROVIDER/MODEL/URL/API_KEY/ALLOW_EXTERNAL; AWS_ROLE_BINDINGS and AWS_DEFAULT_REGION. See `.env.example` and docs/INTEGRATION_CONFIGURATION.md for contracts and exact test prerequisites.

Do not commit `.env`, provider passwords, refresh tokens or private keys. Secrets containing reserved URL characters must be URL-encoded in DSNs. Use a secret manager. `.env.example` contains placeholders. Hosted Supabase URL/publishable key, setup credential and restricted runtime connection are configured locally; other provider keys remain absent. See the live reports for actual evidence.

Additional controls: AUTH_RATE_SECRET; AI_POLICIES; SCIM_BINDINGS; GITHUB_WEBHOOK_SECRET/PREVIOUS_SECRET; GITHUB_SCAN_ACTORS. Supabase setup-only inputs are SUPABASE_PROJECT_REF/DB_HOST/DB_PASSWORD and the included public CA certificate; exclude setup/admin credentials from deployed runtime environments.

## Current migration head

Revision 0022 contains 51 application tables: 50 organization-scoped tables plus self-owned identity_sessions. Additions cover workforce terms/leave, AI accounting, session denial, webhook receipts, cloud evidence/jobs, versioned project review and restricted telemetry retirement. Employment-resolution columns preserve withdrawal history. Later revisions add persisted holiday calendars, versioned risk policies/snapshots, encrypted leased OCR metadata, normalized immutable telemetry and tenant/actor-bound financial cost receipts with reported usage quantities. All tables enable/force RLS; browser roles have no application grants. Runtime cannot directly delete telemetry or update immutable histories. The narrow retirement function validates tenant context and preserves incident evidence.
