# Hosted Supabase deployment

Project: znnyaieilgekmzebewge  
URL: https://znnyaieilgekmzebewge.supabase.co

## Current checkpoint — 26 October 2026

Hosted schema: revision **0025**, **55 forced-RLS application tables** (54 organization-scoped and one self-owned session table), zero metadata differences, restricted runtime role and verify-full pooler TLS. The latest verifiers pass **24 schema/security checks** and **23 rollback-only workflow checks**, plus six separate rollback-only AI-ledger checks. New receipt/event tables deny browser and service API roles; runtime usage/events are SELECT/INSERT only. Durable accounting transactions are proved against disposable PostgreSQL, not by committing hosted financial fixtures. Finding identities are runtime SELECT/INSERT only; browser API roles are denied. All 23 frozen SQL artifacts also apply in chronological order to a fresh disposable PostgreSQL database with the stated Storage catalog fixture.

Revisions 0013–0023 add holiday calendars, encrypted OCR state, retained risk/finance/telemetry evidence, rehire authorization boundaries, narrow project-grant clearing, restricted function ACLs, finding provenance and immutable exact-metadata identities. Reviewed inactive provisioning and restoration use the existing lifecycle/outbox schema. No verifier claims live external SCIM provisioning or a real GitHub App/cloud integration.

Current source passes local Docker Compose service startup, isolation, Linux/PostgreSQL integration, dump/restore and cleanup checks; exact counts/fingerprints are in [Verification](VERIFICATION.md). OS advisory gates still fail. Existing real Auth/MFA/Storage and native service evidence is listed below; public inbox signup/recovery delivery, CAPTCHA/provider administration, real-ID privacy acceptance and production deployment remain pending. The sections below retain earlier dated milestones and do not replace this checkpoint.

## Earlier deployment evidence

The public schema and Storage inventory were empty before deployment. The frozen MESH bootstrap through Alembic revision 0012 committed successfully: 49 application tables plus the migration marker (48 organization-scoped and one self-owned session table). All application tables enable and force RLS; account-session metadata is user-owned rather than employer-owned. Browser roles cannot access backend tables or migration bookkeeping. A separate restricted mesh_runtime role was provisioned and its actual Session pooler login passed. Local backend configuration uses that restricted role, not postgres.

The private mesh-identity bucket allows only PNG/JPEG up to 2 MiB. Four restrictive policies deny direct client object operations. Policy reapplication passed inside a rolled-back transaction. Schema comparison against application metadata returned zero differences. Live tests exercised cross-tenant read/write rejection, context reset, audit hashes and mutation protections, role permissions and anonymous PostgREST denial. Concurrent child transactions completed without deadlock; all synthetic records were removed or rolled back.

Connections use verify-full TLS with the Supabase Root 2021 CA downloaded over HTTPS from https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt. Its CA and hostname successfully verified the pooler. Direct IPv6 remains unavailable; Session pooler works.

## Outstanding provider configuration

- Backend Storage key: configured locally and excluded from deliverables. Positive upload/sign/download plus public/user client denial checks passed; live orphan reconciliation remains unexercised.
- Actual confirmation OTP/login/refresh/TOTP aal2/removal/recovery/password/logout checks passed with a temporary user. Admin-generated tokens replaced inbox delivery. Nine Redis-backed HTTP checks subsequently passed. Full public signup and real inbox/CAPTCHA remain pending.
- CAPTCHA, mail templates/SMTP, refresh-rotation and MFA settings require authorized provider administration and verification. No account management token or browser login is configured.
- ClamAV, Redis and SMTP are not running locally. Uploads and rate-limited business requests fail closed when required services are unavailable.
- TLS is verified by this client; provider-wide SSL enforcement was not changed or independently inspected.

No CLI authentication/linking is claimed. Local .env is excluded from Git and the archive; keep migration-admin credentials out of deployed API environments. The supplied admin password should be rotated before production.

Evidence: supabase-live-results.json and supabase-concurrency-results.json. Run scripts/verify_supabase.py and scripts/verify_supabase_concurrency.py from the configured backend checkout for repeatable checks.

## Later incremental revisions

0004 adds immutable job grades/salary snapshots, reviewed salary changes, leave allowances and analyst notes. 0005 retains model/currency/operator-pricing provenance. 0006 adds self-owned session metadata with immediate MESH revocation. 0007 adds immutable signed GitHub delivery receipts. All are applied and runtime grants refreshed without rotating the runtime credential. Live workflow evidence is in supabase-workflow-results.json; all fixtures were rolled back.

Revisions 0008–0012 add immutable cloud coverage evidence, versioned project approval policies, leased cloud assessment jobs, restricted telemetry retirement and salary-withdrawal history. All are deployed. The 20 deployment checks, nine workflow checks and seven telemetry checks passed again at head 0012. Setup administrator credentials are separate from the runtime backend configuration and excluded from the archive.

Provider acceptance evidence: supabase-provider-results.json (15 checks plus confirmed cleanup). All temporary provider users/files were deleted, application sessions rolled back and no external email sent. See scripts/verify_supabase_provider.py for the reusable fixture driver. It creates a temporary Auth account, enrolls/removes MFA and uploads/deletes a synthetic object; normal Python assertions must remain enabled. It never changes project Auth policy or collects a real identity document.


## Latest runtime acceptance (24 October 2026)

Actual Uvicorn and temporary native Redis passed nine HTTP/runtime checks: readiness 200, real login/MFA/logout, persisted self-session isolation, tenant denial, body limits and account throttling, followed by Redis-outage readiness/business 503. Three separate worker-process checks passed for committed Mailpit delivery, receipt replay without duplication and fixture cleanup. Five ClamAV checks passed using current officially signed definitions, including clean PNG and standard EICAR detection through the upload gate. All temporary services were stopped after testing. Subsequent Docker service, containment and actual Linux scanner acceptance now have separate passing evidence in docker-runtime-results.json and docker-scanner-results.json; the earlier native Windows Semgrep certificate issue does not describe those Linux runs. See PHASE_1_3_STATUS.md for remaining acceptance requirements.
