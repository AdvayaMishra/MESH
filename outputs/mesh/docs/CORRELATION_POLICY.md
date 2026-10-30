# Configurable VADER correlation

Migration 0024 adds immutable tenant-scoped policy versions and optional retained incident policy provenance. Existing incidents are not backfilled or rescored. New incidents retain the effective policy ID/version, algorithm, normalized configuration and SHA-256 configuration digest. Changing a policy does not merge new observations into an incident created under another policy snapshot.

| API | Contract |
|---|---|
| `GET /api/v1/vader/correlation-policy` | Current effective policy; version 0/id null identifies the built-in default |
| `PUT /api/v1/vader/correlation-policy` | Create a new immutable version using `expected_version` and `configuration`; stale edits return 409 |
| `GET /api/v1/vader/correlation-policies` | Paginated version history with total count, including beyond-end offsets |

Security read authority is required for reads and ingestion authority for writes. Active organization/membership/role are refreshed after the tenant lock; a cached revoked analyst role cannot authorize the operation. Policy reads and writes are audited. Database controls include forced RLS, tenant/creator foreign keys, scoped version uniqueness, append-only triggers, browser-role denial and runtime SELECT/INSERT-only policy grants. Incident policy columns reject updates while normal incident transitions remain supported.

Example body, after fetching current version:

```json
{"expected_version":0,"configuration":{"window_minutes":15,"minimum_categories":2,"minimum_events":2,"link_mode":"session_or_resource"}}
```

Configuration supports:

- `enabled` (strict boolean), default true. Disabling correlation does not stop event ingestion or anomaly detection.
- `window_minutes` 1–1440, default 30; event-time window anchored at the latest eligible category for the same actor/tenant/synthetic partition.
- `minimum_categories` 2–13 and `minimum_events` 2–5000, defaults three each. Event threshold must cover the category threshold and fit the evidence limit.
- Unique allowed `categories` from the typed telemetry category set, default all categories.
- `evidence_limit` 3–5000, default 1000 unique anomalous events. Event IDs are limited before weight aggregation; multiple rules on one event consume one slot and contribute only their maximum weight.
- `link_mode`: `legacy`, `actor`, `session`, `resource`, `session_or_resource`. All modes retain the same-actor/tenant/synthetic boundary. Strict session/resource modes never treat two missing values as a shared relationship. The default legacy mode preserves the earlier optional-session gate: an incoming session uses same-session or same-resource links; an event without a session uses the actor/time scope.

The triggering event must participate in the selected anomalous evidence. Excluded, disabled, non-anomalous or out-of-window observations do not create an unrelated new incident. Incident history is bounded by the policy evidence limit; a full accumulated incident can lead to a separate incident rather than unlimited JSON growth.

Telemetry responses now include `correlation_status`: `matched`, `insufficient`, `disabled`, `excluded`, `incomplete` or `not_recomputed`. Exceeding the evidence limit returns `incomplete`, retains the event/anomalies and emits an audited incomplete-correlation event. It does not label the window clean or quietly correlate a truncated sample. Duplicate source receipts remain idempotent and return `not_recomputed`; they do not rerun old telemetry under a new policy. A per-event evaluation ledger is not claimed.

Incident detail/list and graph responses expose retained policy provenance where known. Historic null snapshots remain unknown. The digest identifies recorded configuration; it is not an external audit anchor. Correlation is still a heuristic, not proof of malicious activity, ordered attack-template recognition, a calibrated probability or a comprehensive asset/effective-IAM relationship graph. Investigation and simulated response still require authorized human decisions.
