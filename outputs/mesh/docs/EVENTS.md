# Durable internal events and jobs

Business mutations, audit metadata and normal outbox messages commit in one database transaction. Normal payloads contain `{target_id, version: 1}` and never carry repository source, ID images, names or raw credentials. Organization ID, topic, message ID, creation time, attempts, available_at and state live in separate columns. API clients cannot submit arbitrary event topics/payloads.

Current families include organization creation/verification/status, invitations, employee creation/verification/lifecycle, leave/complaints/departments, project membership/proposals/approvals/comments/sprints/tasks, payroll rules/calculation, finance costs/budgets, repository authorization/scan requests/completion, finding status, security ingestion/anomalies/incidents/cloud assessment and simulated response approval. Event identifiers refer to tenant-scoped domain records. Consumers must recheck scope before loading referenced objects.

The default outbox worker is per-tenant and uses PostgreSQL SKIP LOCKED. General events currently produce idempotent local receipts only; a receipt is not evidence that an external integration ran. Mail topics contain an invitation ID and a Fernet ciphertext holding the recipient/token; the key is external configuration. Mail handling rechecks expiry/status/current token hash before sending and erases ciphertext after processing. Revoked/superseded messages do not send a new credential. The worker uses bounded retries, exponential delay and dead-letter state. `/jobs` exposes metadata only; owner-approved `/jobs/{id}/retry` resets dead-letter delivery.

SMTP is at least once: a crash after external send and before transaction commit may duplicate the same link. Invitation single-use/email binding still prevents replay. No distributed exactly-once guarantee is claimed.

Scanner jobs use a separate persisted queue with tenant/request-key binding, immutable commit, claim lease, three attempts, backoff, stale-result fencing and permission rechecks at claim/completion. Scan output is published only after all configured tools succeed. A failed or partial parser result does not become a clean scan. Resource cleanup is attempted on success/error; the implemented owned-resource janitor requires deployment and live Docker validation.

Configured SCIM offboarding messages invoke a dedicated scim-revocation-v1 consumer after local access revocation and independent approval. It verifies external identity and inactive state, records verified/retrying/failed states and keeps revocation for suspended organizations. Other providers retain explicit manual reconciliation/attestation. No fixture receipt is presented as a live external success. Provisioning and reviewed compensations remain pending.

## Additional durable events

Cloud assessment requests create dedicated tenant-scoped leased job records; terminal reports retain coverage and failure metadata. Project reviews and policy changes append audit/outbox events. security.telemetry.retired contains only the tenant target, version, count and retention days, never retired event content. Account-session denial is self-scoped and contains no access/refresh tokens.


## Local connected startup

The VS Code backend task reads explicit tenant UUIDs from work/final-integration-runtime/mail-organizations.json and supervises a --mail-only outbox worker per listed tenant. This mode excludes all lifecycle/SCIM dispatch. The file currently includes the user-authorized MESH DEMO organization; it does not discover or send for every tenant. Workers share the restricted backend database configuration, mail encryption key and SMTP settings. Workspace-owned TEMP/TMP avoids Windows default temporary-folder heartbeat failures. Stop/restart the owned launcher after changing scope; do not run a second full outbox worker for the same tenant unnecessarily.
