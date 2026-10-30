# Future frontend integration

AWS is optional for running MESH. See [R4 setup/sample contracts](docs/workstreams/R4_STATUS.md) for the three new cloud integration routes. A role-shaped binding is configured_unverified, never connected. Handle not_configured without blocking unrelated screens. Development samples require an explicit endpoint call and a visible sample label; never post them into actual finance records or mix them with live history/totals. No AWS SDK credentials or role-management controls belong in the frontend. The authorized temporary preview handles these states; final frontend implementation remains separate.

A temporary checkpoint frontend is integrated separately; see [preview use and exact limits](docs/TEMPORARY_FRONTEND_PREVIEW.md). The final frontend and full-product acceptance remain pending in IMPLEMENTATION_STATUS.md.

Set the frontend's backend base URL to `http://localhost:8000` in local development. Configure the backend CORS_ORIGINS to a JSON array of exact frontend origins. Wildcards are rejected. Never place database administrator/runtime credentials or service-role keys in browser variables.

1. Register through `/api/v1/auth/register` with email/password/CAPTCHA. Configure CAPTCHA and OTP email templates in Supabase first. Confirm OTP through `/auth/verify` or use supported Supabase client identity flows. Do not create another password database.
2. Hold the provider access token using your reviewed session strategy. Send `Authorization: Bearer …`. Refresh through `/auth/refresh`, complete password recovery through `PUT /auth/password`, and use `/auth/mfa` enrollment/challenge/verification flows. Replace tokens after MFA verification. Production privileged access requires verified aal2. MESH immediately denies revoked observed sessions; logout separately reports whether provider revocation was confirmed. Unseen provider sessions remain provider-dependent. See [Authentication](AUTHENTICATION.md) and `/users/me/sessions`.
3. Create an organization after email confirmation, using `POST /api/v1/organizations` with `{name: "Example Ltd"}`. Save its returned ID as the selected tenant; all tenant APIs also independently validate membership.
4. Send `X-Organization-ID` for tenant calls. Do not use role labels from browser state as authorization. The backend reads membership roles itself.
5. Start a domain challenge, publish its public token both at the HTTPS well-known path and DNS TXT name, then request verification. Both proofs must succeed. The returned status concerns domain control only.
6. Owner invites HR; HR invites developers/analysts. In development, inspect local Mailpit. The invite target signs in with the invited confirmed email and calls `/invitations/accept` with token and target organization header.
7. Generate client types from [OpenAPI](docs/openapi.json) and use [API_REFERENCE.md](API_REFERENCE.md) for the current operation inventory. HR leave/complaints/lifecycle, finance/payroll policies, project collaboration, scan jobs, VADER cloud and model summaries have APIs. Integrations still need configuration and live validation; surface 503 honestly and follow IMPLEMENTATION_STATUS.md for unsupported features. Some aggregate/admin response schemas require final stabilization.

Example request:

```http
POST /api/v1/projects
Authorization: Bearer <access_token>
X-Organization-ID: <selected-organization-uuid>
Content-Type: application/json

{"name":"Inventory service","description":"Proposal for review"}
```

Use `limit`/`offset` for collections. The generated [error contract](docs/ERROR_CONTRACT.md) describes the sanitized `error` envelope, location-only validation fields and request IDs. Display safe messages and use X-Request-ID for support; do not display raw exceptions or log auth bodies. Follow individual operation retry contracts; avoid automatic POST retries after ambiguous responses.

Incident graph response has `incident_id`, `nodes: [{id, category, timestamp}]`, `edges: [{source, target, relation}]`, and explanatory uncertainty text. It is graph-friendly JSON, not proof that an actor is malicious. Risk is a policy score. All response actions remain simulated and require independent analyst approval.

Identity upload is raw JPEG/PNG binary at `POST /employees/{employee_id}/identity-documents`, with exact Content-Type and a 2 MiB limit. Upload requires employee identity and configured ClamAV/private Storage; no OCR automatically approves a document. HR obtains 60-second links from `/hr/identity-documents/{id}/signed-url` and submits human decisions. Never store or log signed URLs. Isolated OCR stays disabled for real documents pending the stated production/privacy checks.

Poll `/scans/{id}` for queued/running/completed/cancelled/dead_letter states, or use the authenticated `GET /scans/{id}/events` SSE contract. `POST /ai/stream` delivers progress/heartbeats and one complete validated insight; it does not stream unvalidated token deltas. Use a streaming fetch client that sends the bearer token and tenant header; avoid putting credentials in query strings. Do not automatically replay/reconnect AI generation after an ambiguous response. [AI streaming](docs/AI_STREAMING.md) documents leases, reauthorization, disconnection and error events. Synchronous `/ai/owner`, `/ai/hr`, `/ai/projects/{id}` and `/ai/vader/{id}` remain available; the local default explicitly identifies itself as deterministic.

For finding history, use [exact-metadata identity APIs](docs/FINDING_IDENTITIES.md). An identity preserves individual scan observations and dispositions; it does not establish a verified fix. Legacy indexing is bounded and requires scan authority. New scan observations start open. For model usage, [monthly summaries](docs/AI_ACCOUNTING.md) keep currencies/models separate and explicitly exclude unrecorded failed or ambiguous charges.

Reviewed rehire and inactive provisioning require separate HR proposals and independent owner reviews. Surface the explicit pending/failed/manual/reconciled states; an accepted job is not proof an external account was created, restored or activated. See [Rehire](docs/REHIRE.md) and [SCIM provisioning](docs/SCIM_PROVISIONING.md). Operator integration secrets stay server-side.

Integration checklist: configured Auth/CAPTCHA/OTP; verified tenant membership; exact CORS origins; reviewed token storage; generated types; 401/403/404/409/422/429/503 handling; authorized role navigation; test data only; PostgreSQL RLS validation; no expectation of unsupported product modules. The supplied checkpoint is integrated as a temporary preview; the final frontend still requires its own mappings and acceptance.

Owner signup may include validated owner_name; current-user name/owner_name are display fields only. See [R1 owner-name contract](docs/workstreams/R1_OWNER_NAME.md).


## Temporary checkpoint frontend — native integration

The supplied checkpoint now uses original navigation and domain screens around the authenticated BFF. See docs/TEMPORARY_FRONTEND_PREVIEW.md for supported flows and docs/native-preview-checkpoint.json for current source/test evidence. New controls include organization proof/invitations, MFA, repository registration/finding review, default risk policies, uncertainty-aware assessments and confirmed synthetic simulation. Backend permissions remain authoritative. This temporary UI does not replace the final frontend acceptance or external provider deployment requirements.
