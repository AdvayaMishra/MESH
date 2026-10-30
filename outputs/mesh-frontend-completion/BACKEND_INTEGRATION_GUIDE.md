# Backend integration guide

> Current connected checkpoint —29October2026: final frontend integration is implemented and locally verified. Default mode uses existing backend APIs; the older demo-only descriptions and test counts below are historical. Build/types pass, lint0errors/6warnings,11Node tests and22connected browser tests pass; backend regression1,280passed/32skipped. Live hosted acceptance is blocked by this session's outgoing database socket restriction (Windows10013), not missing Supabase configuration. See [the current integration guide](docs/FINAL_BACKEND_INTEGRATION.md) and [machine results](verification/final-integration-summary.json). Unsupported/missing backend capabilities remain explicitly unavailable.

This frontend is currently a complete demonstration UI. `lib/api/dataset.ts` and `lib/types/index.ts` define its view models; `lib/api/workspace-source.ts` supplies current demo state after store initialization. Mock fixtures live under `lib/api/mock/`. Stores implement demo mutations. They are not backend authorization or durable storage.

## Confirmed contract source

`docs/backend-openapi.json` is a snapshot copied from the existing local MESH backend, not invented frontend endpoints. Its presence confirms documented route/schema shapes, not live provider acceptance. Generate client types from this snapshot when implementing the live adapter, and compare the backend schema version before deployment.

| Domain | Confirmed route examples | Adapter responsibility |
|---|---|---|
| Auth | `/api/v1/auth/register`, `/api/v1/auth/verify` | Use Supabase-backed identity and reviewed session handling; map provider errors. |
| Organization | `/api/v1/organizations`, `/api/v1/organizations/current` | Verify membership; use the backend organization UUID, not a demo ID. |
| People | `/api/v1/hr/payroll`, `/api/v1/hr/departments` | Preserve restricted-case permissions, independent review and server validation. |
| Engineering | `/api/v1/projects`, `/api/v1/projects/{project_id}` | Map persisted IDs, membership, collaboration and version conflicts. |
| Tasks | `/api/v1/tasks`, `/api/v1/tasks/{task_id}` | Translate view-model fields and refresh affected lists after changes. |
| Scans | `/api/v1/scans`, `/api/v1/scans/{job_id}` | Poll real job states or consume authenticated streaming; never equate queued with completed. |
| VADER | `/api/v1/vader/events`, `/api/v1/vader/events/{event_id}` | Preserve evidence freshness, uncertainty and analyst authorization. |
| Finance | `/api/v1/finance/budgets`, `/api/v1/finance/budgets/{budget_id}/variance` | Keep currencies/periods separate and distinguish estimates from actual charges. |
| AI | `/api/v1/ai/incidents/{incident_id}`, `/api/v1/ai/owner` | Display model/provider provenance and failures; never silently substitute invented results. |

## Transport and session strategy

`createApiClient(baseUrl, session)` in `lib/integration/client.ts` is opt-in. It sends bearer authorization and `X-Organization-Id`, rejects external/redirected paths and credential-bearing base URLs, supports AbortSignal, omits browser cookies and prevents accepting a response after a tenant switch. No base URL, access token or privileged key is built into the demo.

The existing connected preview uses a reviewed same-origin backend-for-frontend and HttpOnly session cookies. Prefer preserving that session strategy when merging this UI into it. Do not put database, service-role, GitHub, Redis or provider secrets in `NEXT_PUBLIC_*`, browser state or shipped files. Never use browser role selection as server authorization.

Implement typed domain adapters against confirmed schemas. Validate network responses at runtime, retain pagination/filter semantics, handle 401/403/404/409/422/429/503 and safe request IDs, and make ambiguous writes visible rather than blindly retrying. Backend membership, object authorization, RLS and audit enforcement are mandatory. Current demo IDs/role labels require explicit mapping to backend IDs/roles.

## Important differences to map

- Demo identity upload accepts JPEG/PNG/PDF up to 5 MiB for local preview. The existing backend accepts raw JPEG/PNG with a 2 MiB limit, private Storage and antivirus checks. The connected mode must enforce the backend limit/types and never retain signed URLs or ID contents in ordinary application state.
- Demo domain verification is an interface preview. The backend requires both DNS and website proofs. An accepted challenge is not verified ownership.
- Demo payroll/promotion/lifecycle decisions never transfer funds or provision accounts. Map independent approval and provider reconciliation states to actual contracts.
- Demo repository animation never clones code or executes Semgrep, Bandit, Gitleaks or OSV. Real jobs require configured backend workers and repository authorization.
- Demo cloud inventory, historical financial/security series and response risk deltas are seeded/illustrative. Unknown actual data must remain unavailable until supplied by the backend.
- Local message, support and ticket drafts do not transmit data. Delivery requires an authorized server-side integration.
- Demo Copilot is evidence-grounded local summarization; planning is explainable arithmetic. Real model services require provider configuration and actual error/usage reporting.
- General notifications/reports/settings must use the final agreed backend capabilities. Do not invent endpoints for features missing from the snapshot.

## Integration acceptance

Merge adapters into the separate connected preview deliberately; retain demo mode as an explicit mode. Exercise two real test tenants, all five roles, session expiry/refresh/logout, restricted cases, object ID tampering, failed writes, retries/concurrency, file limits and provider outages. Replace seeded charts only when the response actually supplies the required data. No hosted accounts, credentials or production changes were created by this frontend release.
