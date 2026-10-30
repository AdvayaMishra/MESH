# Integration configuration and validation



## PostgreSQL



Apply `alembic upgrade head` with a migration administrator, then run `scripts/bootstrap_role.py` with a random MESH_DB_PASSWORD. New revisions preserve 0001. Application/worker connections use the restricted role. Run live tests only on a disposable database whose name begins `mesh_test_`:



```sh

MESH_POSTGRES_ADMIN_URL=postgresql+psycopg://<test-admin>:<secret>@localhost/mesh_test_local pytest -q backend/tests/test_postgres_integration.py

```



Use your shell's secure environment configuration rather than storing actual secrets in commands/history. Tests create a random restricted role, check database-enforced filtering with deliberately unscoped queries, deny cross-tenant writes, reject audit mutation and verify transaction-local context resets. The tests require role creation privileges on the disposable server. The default Windows suite skips these opt-in cases. The integration suite runs against disposable native PostgreSQL and Linux/PostgreSQL; hosted Supabase checks run separately; see SUPABASE_LIVE_STATUS.md and supabase-live-results.json.



## Supabase identity and Storage



Configure SUPABASE_URL, SUPABASE_ANON_KEY, provider CAPTCHA, confirmation OTP policy, refresh rotation, password rules and privileged MFA. Set REQUIRE_PRIVILEGED_MFA=true in production; roles Owner/HR/Security Analyst require verified JWT aal2. Provider logout does not guarantee immediate access-JWT revocation. Configure recovery then use PUT /api/v1/auth/password for completion.



Run `supabase/storage/0001_private_identity.sql` as an authorized Storage administrator. It creates/locks a private mesh-identity bucket, allows only 2 MiB JPEG/PNG and installs restrictive direct-client deny policies. Configure SUPABASE_STORAGE_KEY as a backend secret; never expose it in a frontend. Use the narrowest backend key supported by your deployment and restrict its execution environment. CLAMAV_HOST must point to an updated scanner before uploads can succeed. ClamAV failure blocks uploads. Start the documents Compose profile with CLAMAV_HOST=clamav. Retention is per-tenant, removes expired objects and marks references deleted; review legal holds before real document collection.



The optional live bucket test requires MESH_SUPABASE_TEST_URL, MESH_SUPABASE_TEST_ANON_KEY, MESH_SUPABASE_TEST_STORAGE_KEY, MESH_SUPABASE_TEST_USER_TOKEN and MESH_SUPABASE_DISPOSABLE_TEST_PROJECT=true. It creates one synthetic object, confirms anonymous/authenticated denial and deletes only that test object. Never use a production project. Fixture tests validate application HR authorization without real uploads.



## Email



Set MAIL_ENCRYPTION_KEY from Fernet.generate_key(), SMTP_HOST/PORT/FROM and, for production, SMTP_STARTTLS=true plus SMTP_USERNAME/SMTP_PASSWORD. Keep the encryption key in a secret manager and retain it while queued messages need decryption. Development Mailpit uses SMTP_STARTTLS=false. Invitations queue encrypted credentials in the same transaction as their record; resend rotates the token and invalidates old queued credentials. SMTP is at least once: a crash after send but before commit can duplicate the same link. No plaintext tokens are stored in database payloads. Configure retention/dead-letter monitoring and key rotation before production.



## GitHub and scanners



See SCANNING.md. Configure GITHUB_APP_ID, GITHUB_PRIVATE_KEY (PEM contents in a protected environment secret, not a pathname) and GITHUB_INSTALLATIONS JSON (installation ID â†’ organization UUID). Operator mapping is mandatory to prevent another tenant claiming an installation ID. Build both scanner images on a dedicated Linux Docker host. DOCKER_EXECUTABLE defaults to /usr/bin/docker and must be an absolute trusted path. Do not expose Docker to the API. After builds, run MESH_DOCKER_SCANNER_TESTS=true pytest -q backend/tests/test_docker_scanners.py. The actual Docker engine and hash-locked scanner installation are validated in the approved disposable VM; consult docker-scanner-results.json and docker-runtime-results.json for the distinct runtime acceptance outcomes.



## AWS



Configure the host workload identity and AWS_ROLE_BINDINGS JSON (organization UUID â†’ read-only IAM role ARN), role trust and AWS_DEFAULT_REGION. The adapter assumes a temporary session with a read-only session policy. It never changes infrastructure. Denied inventory/check calls mark the assessment partial/unknown rather than declaring resources safe. Fixture tests call no live cloud API.



## AI



Default AI_PROVIDER=local is a deterministic template. For Ollama set AI_PROVIDER=ollama, AI_MODEL and an explicit local AI_URL ending in /api/chat. For a structured model gateway set AI_PROVIDER=gateway, an HTTPS AI_URL, optional AI_API_KEY and AI_ALLOW_EXTERNAL=true. Gateway POST accepts messages, JSON schema and max_output_tokens; response is `{output:{summary,recommendations,limitations},input_tokens,output_tokens}`. Only numeric aggregates enter model context; no raw repository text, names, ID images or secrets. Gateway/Ollama output is validated and never authorizes employment or enforcement. Costs stay null until a trusted pricing policy exists.



## Identity-document orphan reconciliation



The per-tenant retention worker accepts --reconcile-orphans. It lists only the selected tenant UUID namespace and exact employee/document UUID paths, preserves every durable reference, requires both creation and update timestamps older than 24 hours, aborts before deleting on incomplete inventory, removes at most 50 objects per run, and shares an organization lock with uploads through transaction completion. No orphan deletion has been run against hosted Storage. Configure a backend Storage key first. The API does not expose this maintenance operation to an Owner or employee. Audited document holds and independent release are implemented under0028; production privacy/OCR acceptance remains pending and real OCR processing is disabled. See workstreams/R1_DOCUMENT_PRESERVATION.md for preservation, queue and object-reference controls.



Storage inventory API contract: https://supabase.com/docs/reference/self-hosting-storage/search-for-objects-under-a-prefix . Supabase TLS verification guidance: https://supabase.com/docs/guides/platform/ssl-enforcement .



## SCIM offboarding adapter

Current concurrency requirement: each binding defaults to `require_version=true`; state-changing PATCH requires the verified resource `ETag`/`meta.version` as `If-Match`. Missing or conflicting versions fail closed, and a provider precondition failure never falls back to an unconditional update. Only an explicitly configured `require_version=false` supports a versionless legacy provider with weaker race protection. See [current SCIM version and TLS acceptance details](workstreams/R1_R4_LIVE_CONFIGURATION.md#conditional-scim-updates). This applies to both deactivation and opt-in restoration.



Set SCIM_BINDINGS as organization UUID -> {base_url: fixed HTTPS SCIM tenant root, token: backend bearer credential}. Each endpoint is bound to one organization. HR links a SCIM user via POST /api/v1/hr/employees/{id}/scim-account; the provider's id and userName must match the selected employee membership. Only independently approved offboarding queues lifecycle.scim.revoke after local revocation. The outbox consumer checks current owner authorization, never restores access, verifies the account before PATCH active=false and re-reads inactive state. Transient errors retry; terminal errors require manual review. Existing non-SCIM steps remain manual. No live SCIM operation was performed. Protocol: https://www.rfc-editor.org/rfc/rfc7644#section-3.5.2 .



## AI admission and price estimates



External/gateway/Ollama use requires AI_POLICIES per organization with matching provider/model. Example operator policy: {provider: gateway, model: configured-model, monthly_requests: 500, monthly_input_units: 1000000, monthly_output_units: 200000}. Optional input_price_per_million/output_price_per_million/currency must be configured together; monthly_cost_limit requires pricing. Rates are administrator-entered estimates, not vendor price discovery. Each request reserves admission headroom for 4096 input and 800 output units while serializing that tenant. Actual reported units must be bounded; saved records retain model, currency and pricing provenance. Unknown/mixed current-month costs fail closed for cost admission. Failed/rolled-back requests can incur unrecorded upstream charges, so this is not a provider hard spending cap. No external paid model provider was called; an actual local Ollama model was exercised separately (docs/ollama-live-results.json).



## GitHub webhooks



Configure GITHUB_WEBHOOK_SECRET (32+ random characters), optional GITHUB_WEBHOOK_PREVIOUS_SECRET during rotation, and operator-owned GITHUB_INSTALLATIONS. Register the deployed HTTPS /api/v1/webhooks/github with the App; no public endpoint is deployed from this laptop. Optional GITHUB_SCAN_ACTORS maps organization UUID to an active authorized senior developer/security analyst. Signed push events queue only already-authorized repositories and exact commits. Delivery IDs and payload hashes bind replay; commit keys avoid duplicate push scans. Installation suspension/deletion and repository removal disable local grants and cancel/fence jobs. Additions/unsuspension require owner review. The raw 1 MiB envelope is never persisted. Real GitHub credentials/webhook delivery remain untested. Sources: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries and https://docs.github.com/en/webhooks/webhook-events-and-payloads .



## Account session security



AUTH_RATE_SECRET is an independent 32+ character secret, required in production and for real session observations. Redis still must run. Verified JWTs require a UUID session_id; self-owned identity_sessions RLS uses mesh.user_id. GET /api/v1/users/me/sessions and revoke-one/revoke-others require bearer identity, without an organization header. These immediately deny observed sessions throughout MESH; they do not independently revoke provider refresh credentials. Logout now returns HTTP 200 with mesh_sessions_revoked and provider_logout=confirmed/unavailable, retaining local denial when the provider fails. Never treat a client hint as trusted device attestation. Session tombstones are not deleted automatically, because a refresh credential might otherwise resurrect access. Provider session reference: https://supabase.com/docs/guides/auth/sessions .



## Continuation configuration and validation boundaries



The hosted schema is at Alembic 0022. Local administrator setup inputs are in workspace work/supabase-setup.env, outside the backend folder; verifiers accept MESH_SUPABASE_SETUP_FILE to select a different secure setup file. API/worker .env uses only mesh_runtime. Use certificate-verified Session-pooler TLS. The Docker image includes the public CA at /srv/mesh/supabase/supabase-ca.crt; configure the container DATABASE_URL sslrootcert to that path rather than a Windows host path.



PrivateStorage supports opaque sb_secret_* backend keys using apikey only. Legacy service-role JWTs additionally use Authorization: Bearer. Publishable keys are rejected as private-storage authority. The backend Storage key is now configured in local .env and verified against Auth administration and Storage; it is excluded from archives. Never expose either backend key to a browser. See [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys).



AWS assessment jobs use the optional cloud-worker Compose profile and require explicit per-tenant AWS role bindings. Claims and completions recheck active authorization; crashes retry at most three attempts. Results record incomplete permissions/coverage. Fixture tests do not establish AWS access. AWS_KEY_MAX_AGE_DAYS defaults to 90; this is an operator policy, not proof of compromise.



TELEMETRY_RETENTION_DAYS is a JSON organization-UUID-to-days map (30–3650), empty by default. Run python -m app.maintenance --organization UUID --telemetry-only --once only after configuring the organization's approved policy. This retires old uncorrelated telemetry and child anomalies in bounded batches; incident-linked evidence and audit history remain retained. No customer telemetry was deleted in verification. Document orphan reconciliation remains a separate explicit mode requiring backend Storage authority.


## Verified provider journey

Run python scripts/verify_supabase_provider.py only against the operator-approved configured project. It creates one uniquely marked unconfirmed Auth user, generates confirmation/recovery OTPs through the admin API without email delivery, verifies provider sessions and real TOTP, checks private Storage/client denial and deletes its own user/file. Database session observations roll back. An external workspace fixture ledger prevents further runs when cleanup is unresolved. Evidence: supabase-provider-results.json. The driver uses normal Python assertions; do not run with -O.


## Latest runtime acceptance (24 October 2026)

Actual Uvicorn and temporary native Redis passed nine HTTP/runtime checks: readiness 200, real login/MFA/logout, persisted self-session isolation, tenant denial, body limits and account throttling, followed by Redis-outage readiness/business 503. Three separate worker-process checks passed for committed Mailpit delivery, receipt replay without duplication and fixture cleanup. Five ClamAV checks passed using current officially signed definitions, including clean PNG and standard EICAR detection through the upload gate. All temporary services were stopped after testing. Docker engine build/startup and containment remain unvalidated. Native Semgrep passed the three bundled rules using the official core with documented legacy workers under approved execution. See PHASE_1_3_STATUS.md for exact remaining access requirements and reproducible commands.


Latest continuation: all three native scanner tools passed trusted synthetic fixtures; registry lockfile coverage now includes Pipenv/Poetry/uv. The combined real-provider document journey passed 19 checks with rollback-only database fixtures and verified external-object cleanup. Six container source images are frozen by verified manifest digest. See docs/PHASE_1_3_STATUS.md and the corresponding JSON evidence for limits.


## Current local acceptance commands

The reusable scripts/verify_native_postgres.py driver takes --postgres-bin, --workspace and --disposable-local-cluster. Supply an absolute trusted PostgreSQL bin directory and a workspace directory. It creates its own loopback/SCRAM cluster, executes the three PostgreSQL integration cases, checks dump/restore equivalence and removes its fixtures. It never installs a Windows service or reads hosted .env.

scripts/verify_docker_clamav.py requires absolute --docker-executable, --compose-executable, --definitions and --workspace paths, a trusted --probe-image, and --dedicated-disposable-docker-host. The definitions directory must contain main.cvd, daily.cvd and bytecode.cvd. Each is digitally verified inside the pinned Linux image, and daily must be younger than 72 hours. The driver starts only a generated Compose ClamAV service, scans a synthetic PNG and in-memory standard EICAR through the real upload malware gate, checks outage failure and removes its resources. No scanner port is published. It temporarily disables FreshClam and bounds scan threads/queue for a reproducible test; ongoing production updates remain required. Evidence: clamav-container-results.json.

scripts/verify_docker_runtime.py supports --prebuilt-backend-image only after resolving its immutable image ID and verifying both copied and imported application source plus exact runtime versions. With --offline-wheels, the checked cache is copied into the disposable test image; it does not modify a supplied production runtime image. Every project, credential, tenant and volume is generated locally. A synthetic identity URL is used for configured-readiness checks only; real Auth/MFA/Storage acceptance is separate.

scripts/verify_scanner_recovery.py validates stale keeper/container/volume recovery, dry-run safety, recent/unowned preservation, idempotency and fixture cleanup on an explicitly opted-in dedicated host. It does not simulate a host crash. Never replace these scoped drivers with Docker prune or point disposable PostgreSQL tests at hosted data.


## Holiday policy and OS image assessment continuation

Revision 0013 adds an empty-by-default holidays JSON field to leave_entitlements without changing RLS or grants. PUT/GET /api/v1/hr/employees/{employee_id}/leave-allowance/{year} now accepts/returns a bounded holidays array of unique ISO dates in that year. Holidays subtract from calendar and weekday charges. Calendar changes are blocked while pending/approved reservations exist, including zero-charge leave. This is explicit per-employee configuration; automatic accrual, carry-over, organization-wide calendars and jurisdiction rules remain pending.

Run scripts/audit_debian_image.py --docker-executable ABSOLUTE_DOCKER_PATH --image TRUSTED_OPERATOR_IMAGE --trusted-operator-image --output REPORT_PATH. It resolves an immutable image ID, runs a read-only UID 10001 no-network/no-mount probe, maps installed Debian source names/versions, and sends only that public metadata to OSV. It exits nonzero on advisory matches or incomplete assessment. It is not a sandbox for arbitrary repository images. Current backend/scanner reports each contain 69 matches; independent applicability review/remediation is pending and the CI OS gates intentionally fail until resolved. Do not suppress these to claim completion. References: https://ossf.github.io/osv-schema/ (Debian source-name/release semantics), https://google.github.io/osv.dev/api/ (query API).


## Durable AWS billing collections

See [R4 billing contract](workstreams/R4_BILLING_COLLECTIONS.md) for the five finance-authorized APIs, opt-in billing-worker profile, separate AWS_BILLING_ROLE_BINDINGS, one-attempt provider configuration, immutable reports and explicit uncertain outcomes. Current live prerequisites are recorded in [R1/R4 configuration boundary](workstreams/R1_R4_LIVE_CONFIGURATION.md).
