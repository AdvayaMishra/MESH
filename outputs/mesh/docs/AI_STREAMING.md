# AI streaming contract

`POST /api/v1/ai/stream` requires the same bearer token, organization header, MFA and resource permission as the corresponding JSON summary. Body: `{"purpose":"hr"}` or `{"purpose":"devtrack","target_id":"<project-uuid>"}`. Owner/HR summaries forbid target IDs; devtrack, vader and risk require their respective project, incident or risk-assessment UUID. Arbitrary prompts, documents, logs and context are rejected.

Response content type is text/event-stream, Cache-Control no-store, X-Accel-Buffering no. Use a streaming fetch POST that supports Authorization and X-Organization-ID headers. Native browser EventSource does not supply this POST/header contract. No token belongs in a URL.

Events:

```
event: state
data: {"state":"generating","contract":"mesh-ai-sse-v1"}

: keepalive

event: result
data: {"provider":"...","summary":"...","recommendations":[],"limitations":["..."],"usage":{...}}
```

The result is one complete schema-validated InsightOutput. State and comment heartbeats describe ongoing work; they are not token deltas or percentage estimates. Partial/unvalidated model JSON is never delivered. On a post-header failure, the stream instead ends with `event: error` and data containing `code` and `automatic_retry:false`. Codes are generation_unavailable, quota_or_policy_limit or authorization_or_dependency_unavailable. Initial permission/target/admission errors use ordinary HTTP errors before streaming starts.

One Redis lease is admitted per organization member, separate from scan-stream leases. It has an independently expiring 60-second TTL, is renewed during work/drain, and uses token-checked renewal/release. A concurrent stream receives 429/Retry-After; Redis outage fails closed. Session denylist, expiry, organization, membership, MFA, role and target scope are checked during progress and immediately before final delivery. Rechecks are read-only and do not retain a session-refresh lock during model inference.

Do not reconnect automatically, replay a POST after an ambiguous failure, or treat this as a resumable job. There is no durable response replay or Last-Event-ID support. Disconnecting stops delivery. An already dispatched provider POST cannot be safely undone; the worker drains that one call and commits successful usage independently of the response. It keeps the lease during drain and never regenerates automatically. Configure bounded database statement/lock timeouts as well as proxy/server request limits. The HTTP model adapter has a 30-second overall budget checked across attempts/headers/chunks plus a 15-second individual blocking-I/O timeout; an active blocking operation can overrun the budget until its I/O timeout.

Usage is an estimate using configured pricing, not a vendor invoice or hard external spending cap. For PostgreSQL-backed paid calls, durable dispatch/reservation records survive caller rollback and retain uncertainty after failure; owner-only receipts support explicit provisional reconciliation. Actual vendor amounts remain unknown until separately verified. No insight/result payload is persisted or replayed. See AI_ACCOUNTING.md. This contract performs advisory generation only and cannot approve employment/payroll or execute security actions.

Actual Redis + ASGI template acceptance: ai-stream-live-results.json. Actual local model inference/schema/quota/outage acceptance: ollama-live-results.json. These are separate proofs; neither establishes production model quality, network HTTP throughput, or real Supabase authentication for this route.
