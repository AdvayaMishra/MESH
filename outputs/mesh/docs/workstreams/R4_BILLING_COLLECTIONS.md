# Durable AWS billing collections - backend contract

Current R4 delivery: see [R4 status](R4_STATUS.md) for AWS-optional setup/status APIs, development samples and verified handoff scope. The implementation details and earlier checkpoints below remain valid within their stated scope. Real AWS acceptance remains deferred/unverified until connected.

Implemented R4 workflow, additive schema revision **0027**. This is an account-filtered observation feed, not invoice verification or automatic bookkeeping. Existing manual cost records are unchanged. No frontend implementation is included.

## API

All routes require the normal bearer identity, `X-Organization-ID`, current finance authority, an active organization/member and an active tracked identity session outside isolated test fixtures. Production privileged MFA applies. Only the owner role currently has finance permissions. Request/cancel require `finance.write`; history/detail/report require `finance.read`. Authorization is refreshed before each operation; foreign/missing IDs return the same 404.

Base path: `/api/v1/finance/cloud-billing/aws/collections`.

| Method/path | Behavior |
|---|---|
| `POST /` | Admit a collection; 202 returns its durable status. Body: `request_key` UUID and `period` (`YYYY-MM`) only. |
| `GET /` | History page: `items`, `total`, `limit`, `offset`, `next_offset`; optional exact `period`, limit 1-100, offset 0-100000. Empty offset pages retain totals. |
| `GET /{collection_id}` | One status record; no provider credentials, raw errors or report blob. |
| `POST /{collection_id}/cancel` | Cancel queued/running work; already-dispatched provider calls may finish, but their result is discarded. Terminal jobs return 409. |
| `GET /{collection_id}/report` | One immutable `AWSBillingReport`; 409 until a completed report is available. Amounts are exact decimal strings. |

POST example (illustrative period; use a month within the current twelve calendar months):

```json
{"request_key":"de6a4b32-f14a-4623-8f57-e0183031083e","period":"2026-10"}
```

The client generates and retains one UUID per deliberate collection. Replaying that key with the same actor/period returns the existing record without another provider call; another actor/period conflicts with 409. A replay still works after a period ages out or a binding is removed, because it does not start new work. An explicit new request key is required to re-collect a failed/ambiguous/completed period. Do not generate a new key automatically after a timeout.

Admission is limited to three pending collections and twenty admissions per UTC day per organization, serialized by the existing tenant lock. Replays are checked before quotas. Synthetic fixtures neither consume production quotas nor run through the billing worker/normal history. The request does not accept an account, role ARN, credentials, synthetic flag, vendor report or amount. The operator binding determines the account.

Status fields: `id`, `period`, `provider_account_id` (12-digit string), `status`, `attempts`, `error_code`, `created_at`, `dispatched_at`, `finished_at`, and `provider_queries_may_incur_charges=true`. `attempts` is collection dispatch count (0/1), not the number of vendor HTTP pages or a measured charge.

States: `queued`, `running`, `completed`, `failed`, `ambiguous`, `cancelled`. Error codes are sanitized: `cancelled_by_owner`, `authority_revoked`, `billing_binding_changed`, `period_out_of_window`, `dispatch_outcome_unknown`, `provider_unavailable_or_invalid`, `provider_scope_or_time_mismatch`. No raw provider exception is exposed. Standard MESH request-ID/error envelopes and 401/403/404/409/422/429/503 behavior apply. A missing separate billing binding prevents new admission with 503; failure is never represented as a zero-cost report.

Reports retain the organization/account/period, inclusive start/exclusive end dates, `UnblendedCost`, provider `estimated` flag, collection time, service/currency observations and currency-separated exact totals. Refunds/credits can be negative. `invoice_verified` is always false. There is no currency conversion, cross-unit usage sum or automatic posting into nonnegative manual costs. Multiple collections for a month are independent observations; do not add successive snapshots together as if they were separate invoices.

## Worker, integrity and failure handling

Run one explicitly scoped worker per authorized organization:

```text
python -m app.billing_worker --organization <organization-uuid> --loop
```

Compose profile: `docker compose --profile billing up -d billing-worker`. Set the existing `WORKER_ORGANIZATION_ID` to the actual organization. The worker has its own private heartbeat and cycle deadline, runs as UID10001 with read-only root/capabilities dropped, and is included in Compose acceptance.

1. Claim under the tenant/job lock, refresh active finance membership/session and configured binding, validate the period and commit `running`, a unique dispatch token, dispatch time and five-minute lease.
2. Release the database transaction before external reads. The adapter queries only the verified assumed account, uses monthly SERVICE grouping and caps pages/records/bytes/soft time. Cost Explorer SDK retries are disabled (`total_max_attempts=1`).
3. Reacquire the tenant/job lock and verify current status/token/lease, requester authority/session and binding. Revalidate the complete provider DTO, its exact totals, provenance and organization/account/period/time before publishing.
4. Publish the report and completed status atomically. Cancelled/revoked/changed/expired attempts cannot publish. Provider/validation failure is terminal `failed`; expired dispatched work becomes `ambiguous`, with no automatic provider repeat. A separate explicit owner request may re-collect.

A process crash after dispatch may mean the provider performed a charged read even if no result was retained. Recovery preserves that uncertainty. The same durable job is never automatically dispatched twice. One collection can require multiple provider pages; it is not a provider invoice or exact API-fee ledger.

`billing_collections` reuses MESH tenant rows and composite organization/requester and requester/session foreign keys. Forced RLS scopes all rows. Database guards freeze admission, dispatch ownership and every terminal record, enforce report tenant/account/period/provenance binding, and deny deletion. Supabase API roles have no table/function grants; the restricted runtime has SELECT/INSERT/UPDATE, without DELETE. Terminal UPDATE is denied by the guard. Existing migrations through0026 remain frozen. New frozen SQL: `20261026000400_billing_collections.sql`.

Audit/outbox events contain only the collection target ID/version: `finance.billing.requested`, `dispatched`, `completed`, `failed`, `ambiguous`, `cancelled`. Report/list/detail reads are audited. No financial report, credential, raw ARN policy or identity token is placed on the general event bus. Reports are byte-bounded and are not loaded into history pages.

## Operator configuration and remaining live acceptance

The billing adapter sends the canonical MESH organization UUID as STS `ExternalId`, validated before SDK credential access. The target role trust must require this tenant value plus the approved source principal. No caller-supplied external-ID override or fallback is accepted. The prepared CloudFormation role template enforces this condition; live correct/omitted/wrong-ID role assumption checks remain mandatory before customer acceptance. Existing trusts expecting a different value require operator migration. See [role setup guide](../../infrastructure/aws/README.md).

Use a separate `AWS_BILLING_ROLE_BINDINGS` mapping from canonical MESH organization UUID to an approved commercial-AWS IAM role ARN. Posture `AWS_ROLE_BINDINGS` are not reused. Configure a trusted source credential chain (workload IAM identity or securely supplied short-lived AWS SDK credentials/profile), role trust permitting assumption, Cost Explorer activation/access and `ce:GetCostAndUsage` on the target role. The backend independently queries STS identity with the assumed credentials before constructing Cost Explorer. Source identity, database/admin credentials and provider tokens stay out of the repository/API/chat.

The provider filter is the verified role account, including when the role is in an AWS management account. It does not silently authorize consolidated member accounts. Other AWS partitions, multiple account selection, Azure/GCP billing and verified vendor invoices are not claimed by this v1 workflow.

For a real acceptance run after authorized configuration: submit one controlled period, observe queued/running/completed status with the billing worker, read the report, compare its account/period/metric/currencies/estimated values against the authorized provider view, replay the same key and confirm no redispatch, test cancellation/revocation using dedicated fixtures, and review audit/job outcomes. Provider queries can incur AWS charges. No live provider run was performed by local or hosted-schema tests.

Verification evidence is recorded in IMPLEMENTATION_STATUS.md and machine-readable reports. Hosted fixtures always roll back and are explicitly synthetic; they do not establish real Auth or cloud acceptance. OS advisory/production clearance gates remain separate.

## Verified checkpoint

Windows908/28, Linux934/2 with26 actual PostgreSQL cases, all ten Compose gates and restore0027 pass. The billing worker's actual process/private heartbeat/container healthcheck passed with an empty queue; provider behavior is separately tested with synthetic SDK fixtures. Supabase0027 is deployed,56 application tables have forced RLS, all25 frozen SQL artifacts apply fresh, and nine hosted rollback-only billing checks pass with zero metadata differences. Ruff/format/mypy91/Bandit and41-pin UID10001 runtime artifact checks pass. The backend OS gate remains failed on69 advisory references. No real AWS billing query, invoice or production identity journey is claimed.
