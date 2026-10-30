# AI dispatch receipts and provisional accounting

Migration 0025 adds tenant-scoped `ai_requests` and append-only `ai_request_events`. Existing `ai_usage` records gain nullable receipt/admission-period links; legacy rows are preserved without backfill. Request intent/pricing/model/provider are immutable, dispatch ownership is fenced, and successful usage/events deny runtime UPDATE/DELETE. Browser and service API roles cannot access the new financial tables directly. Backend routes enforce the current tenant and owner finance permission; privileged MFA remains required by production configuration.

## Dispatch and settlement

PostgreSQL-backed nonlocal generation commits a reservation, then a dispatch marker before invoking the provider adapter. These use independent transactions and a separate process-owned pool (two connections, no overflow, two-second checkout limit), so occupied API connections cannot starve accounting. Transactions set five-second statement and two-second lock limits. The caller's business/audit/session transaction is never committed merely to account for a model call. Application shutdown disposes the accounting pool after work drains; changed database authority requires process restart. Budget for these two additional connections per API process.

Admission serializes through a per-tenant advisory transaction lock and counts successful paid usage, active reservations and separately reconciled attempts without double counting. Known local deterministic templates do not consume paid admission. Provider/model/pricing/credentials/endpoint configuration is captured before dispatch; prices come from the operator snapshot, never model-reported money. No raw prompt/context/result, API key or URL is stored in a receipt; only bounded aggregate-context and endpoint digests are retained privately.

Success atomically inserts linked immutable usage and settles its receipt. Identical settlement cannot duplicate usage. Caller rollback or disconnected delivery does not erase committed accounting. A lost/invalid response, counter/provider mismatch or failed settlement retains `dispatched`/`ambiguous` uncertainty and conservative reserved units/cost. Larger valid observed counters/amounts increase admission conservatively. Only the trusted adapter's known pre-send configuration/connection failure releases an attempt as `not_dispatched`. Connection-only retry remains bounded to two attempts; response/read/schema errors never regenerate automatically.

The accounting pool is idle during inference, but existing caller tenant/member locks remain held through generation. Concurrent tenant operations and receipt reads can wait behind a model call; configure database/proxy deadlines and evaluate real inference latency under load. Local service tests do not establish production throughput.

## Owner endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/ai/requests` | Tenant-only receipt page, optional state filter, bounded limit/offset and preserved total |
| GET | `/api/v1/ai/requests/{request_id}` | Receipt plus bounded ordered event history and preserved event total |
| POST | `/api/v1/ai/requests/{request_id}/cancel-expired` | Cancel only an expired reservation that has never dispatched |
| POST | `/api/v1/ai/requests/{request_id}/reconcile` | Explicit actor/body-bound provisional charge/no-charge report |

Successful insight usage includes `request_id` (null for local/legacy accounting). Receipt DTOs exclude dispatch tokens, private digests and policy snapshots. Reads and owner actions append scoped generic audit records; financial events commit with accounting even if the caller audit transaction later rolls back.

A reservation expires for pre-dispatch cancellation after 60 seconds. Dispatch fences competing cancellation and sets a 90-second review deadline. Crossing UTC admission months before dispatch cancels without sending. Dispatch/ambiguity is never automatically released or resent after a timeout or process restart. The owner must attest that the worker stopped and provider billing was reviewed before reconciling an expired dispatched/ambiguous request, supplying a bounded reference. A reported charge requires both strict usage counters, bounded amount and uppercase currency. A no-charge report omits measurements instead of inventing zero usage. Replays bind the exact validated body and actor; changed reports return 409. A late provider observation reopens uncertainty, preserves conservative known amounts and retains the prior immutable owner report.

All receipt outputs state `provider_invoice_verified:false` and `amounts_are_provisional:true`. Owner attestation is not a verified vendor invoice. Reconciled failed charges remain in the request ledger, not the successful-usage table. No-charge reconciliation releases reserved units/cost but retains the dispatched-attempt request count.

## Successful usage and integration limits

`GET /api/v1/ai/usage/summary` remains successful-only, grouped by provider/model/currency. It reports `failed_or_ambiguous_dispatches_included:false` and `provider_invoice_reconciled:false`; consult receipts for uncertainty and owner reports. New linked usage is attributed to the UTC admission month, with a composite receipt/month FK. Legacy rows use their UTC creation month. Periods are half-open, currencies are never combined, and unknown costs remain explicit. Observation history adds receipt/admission-period fields without changing existing fields.

Paid gateway/remote dispatch fails closed without PostgreSQL. Deterministic templates and explicitly local, nonexternal loopback Ollama may use SQLite; those local CPU calls have no external provider charge. Unit tests use an explicitly injected SQLite accounting double, never a product TEST_MODE durability bypass. Actual independent commits, caller rollback survival and pool saturation are proved separately on PostgreSQL.

Existing synchronous summary and POST SSE contracts remain available. Clients must initiate generation deliberately and must not prefetch/replay generating GETs or automatically reconnect/retry an ambiguous generation. No insight/result is persisted, no completed response can be resumed, and no vendor idempotency or invoice connector is claimed. Historical missing/failed charges are not reconstructed. Operator estimates, conservative reservations and owner reports are not a guaranteed external spending cap.

## Evidence

Windows unit/API/schema tests cover privacy, strict attestations, quota retention, over-bound observations, trusted pre-send release, owner/tenant denial, pagination, UTC month fencing and repeat-safe owner actions. Actual PostgreSQL cases prove commit-before-provider-boundary, survival after caller rollback, a fully occupied one-connection API pool with separate accounting capacity, concurrent admission, cancellation/reconciliation fencing, late observations, tenant/period FKs and database mutation rejection. Full frozen SQL applies to a fresh PostgreSQL database, reproducing permissive API defaults before the new migration to test revocations.

Hosted Supabase migration/RLS/grant/trigger/metadata checks pass. Six separate hosted ledger fixtures all roll back; they do not pretend to prove independent commits by retaining hosted financial test data. No paid model, provider invoice or real payment was exercised. Consult current verification JSON for exact suite counts and image fingerprints; production security clearance remains false.
