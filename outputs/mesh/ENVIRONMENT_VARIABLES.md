# Environment variables

| Variable | Purpose |
|---|---|
| DATABASE_URL | SQLAlchemy PostgreSQL DSN; runtime must be non-owner/non-BYPASSRLS |
| POSTGRES_ADMIN_PASSWORD | Compose migration administrator only |
| MESH_DB_PASSWORD | Random 24+ character URL-safe runtime role secret |
| SUPABASE_URL | HTTPS provider base URL, issuer derived as /auth/v1 |
| SUPABASE_ANON_KEY | Auth API anon key; no service-role key required |
| JWT_AUDIENCE | Expected access token audience; default authenticated |
| REDIS_URL | Private shared rate limiter; production requires authenticated `rediss` with certificate and hostname verification. URL options disabling verification are rejected. |
| CORS_ORIGINS | JSON array of exact allowed browser origins |
| ENVIRONMENT | development or production; production forbids test mode |
| TEST_MODE | false outside automated tests; permits isolated SQLite fixtures and bypasses rate limiter only |
| MAX_REQUEST_BYTES | Default 262144-byte body cap |
| SMTP_HOST, SMTP_PORT, SMTP_FROM | SMTP transport; production also requires authenticated STARTTLS |
| INVITATION_BASE_URL | Fixed HTTP(S) acceptance endpoint without credentials, query, fragment, backslashes or whitespace. HTTPS required when production SMTP is enabled; token delivered only by email. |
| WORKER_ORGANIZATION_ID | Explicit authorized tenant for Compose worker profile |
| CLAMAV_HOST, CLAMAV_PORT | Malware endpoint; port1–65535. Production remote plaintext is rejected; explicit loopback service/sidecar is permitted. |
| CLAMAV_TLS | Enable verified TLS to the malware endpoint; false by default for development clamd. |
| CLAMAV_CA_FILE | Optional absolute CA path; empty uses system trust. Provision it at the same path in the deployed API/worker context. |
| CLAMAV_TLS_SERVER_NAME | Optional fixed certificate DNS name when connecting through a different transport address; hostname verification remains enabled. |
| MESH_PUBLIC_URL | Offline production gate: public HTTPS application origin; not a credential or automatic deployment setting. |
| MESH_BACKEND_IMAGE | Deployment scaffold: reviewed backend repository@sha256 image reference. |
| MESH_TRUSTED_PROXY_IPS | Deployment scaffold: exact trusted ingress IPs; wildcard/network-wide trust is rejected by the gate. |

Additional implemented configuration: MAIL_ENCRYPTION_KEY; SMTP_STARTTLS/USERNAME/PASSWORD; REQUIRE_PRIVILEGED_MFA; SUPABASE_STORAGE_KEY; CLAMAV_HOST/PORT; GITHUB_APP_ID/PRIVATE_KEY/INSTALLATIONS; SCANNER_IMAGE; DOCKER_EXECUTABLE (absolute trusted path); AI_PROVIDER/MODEL/URL/API_KEY/ALLOW_EXTERNAL; AWS_ROLE_BINDINGS and AWS_DEFAULT_REGION. See `.env.example` and docs/INTEGRATION_CONFIGURATION.md for contracts and exact test prerequisites.

Do not commit `.env`, provider passwords, refresh tokens or private keys. Secrets containing reserved URL characters must be URL-encoded in DSNs. Use a secret manager. `.env.example` contains placeholders. Hosted Supabase URL/publishable key, setup credential and restricted runtime connection are configured locally; other provider keys remain absent. See the live reports for actual evidence.

Additional controls: AUTH_RATE_SECRET; AI_POLICIES; SCIM_BINDINGS; GITHUB_WEBHOOK_SECRET/PREVIOUS_SECRET; GITHUB_SCAN_ACTORS. Supabase setup-only inputs are SUPABASE_PROJECT_REF/DB_HOST/DB_PASSWORD and the included public CA certificate; exclude setup/admin credentials from deployed runtime environments.

SCIM_BINDINGS entries accept allow_provisioning and allow_activation, both false by default. Configure them only for an authorized, validated fixed provider authority. See docs/SCIM_PROVISIONING.md and docs/REHIRE.md.
