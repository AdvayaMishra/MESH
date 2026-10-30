# Invitation listing and delivery status

GET /api/v1/invitations supports limit (1–100), offset and status=pending|accepted|revoked. Results contain invitation reference, recipient email, assigned role, invitation status and expiry. No token, hash, encrypted payload or provider error is returned. Ordering is created_at descending then ID. Owner can read organization invitations; HR sees only developer/security invitations; other roles are denied. Requests remain tenant-scoped and audited. Expiry is represented by expires_at; a pending row may have expired without being accepted or revoked.

GET /api/v1/invitations/{invitation_id}/delivery returns metadata for the latest mail queue entry. It does not send or resend email.

| State | Meaning |
|---|---|
| not_queued | No invitation mail job was found. |
| queued | Pending first transport attempt. |
| retrying | A prior attempt failed; a later attempt is scheduled. |
| failed | Dead-letter state; inspect/retry through the existing authorized job workflow. |
| smtp_accepted | The mail transport returned successfully for the current token. This does not prove inbox delivery. |
| skipped | The worker deliberately skipped an inactive, expired or superseded invitation. |
| processed_unknown | A historical processed message lacks retained transport-outcome evidence. Do not display it as sent. |

The response also includes job_id, attempts, queued_at, next_attempt_at, processed_at when a receipt exists, a bounded outcome and inbox_delivery_verified=false. A resend creates a new queue entry; the endpoint follows that newest entry instead of reporting an older send as the replacement's status.

New worker runs retain only the invitation reference and sanitized outcome after processing; ciphertext is erased. Token/hash and encrypted recipient binding are checked before SMTP. Transient failures retain encrypted retry material and expose no raw exception. Legacy receipt replay cannot retrospectively prove SMTP acceptance. SMTP is still at least once: a crash after external acceptance but before commit can duplicate the same single-use invitation. There is no exactly-once guarantee.

These are backend APIs. The current frontend still uses manual invitation references until its controls are updated to consume the new list/status APIs. Existing routes and request shapes remain supported; no schema migration was required.


## Fresh issuer authority and expiry

Creation, resend and cancellation recheck the acting member after acquiring the tenant lock. Acceptance rechecks the original/current issuer's active membership and role permission, and refreshes organization status after the lock. An old link cannot grant membership after its issuer loses the required invitation authority. A permitted replacement issuer may resend; that rotates the token and records the new issuer, preserving original creation/resend audit history. Existing role separation remains: owner invites HR, HR invites developers/security analysts.

The worker checks issuer authority immediately before a transport attempt and skips unauthorized links. It cannot retract a message already accepted by SMTP, and revocation may race an in-flight external send; acceptance remains the authoritative gate. SMTP acceptance is not proof that a currently revoked link is usable. Invalid/expired/superseded/unauthorized messages are not retried as newly authorized invitations without an authorized resend. Expiry compares UTC instants, preserving non-UTC offsets instead of replacing their timezone.

No Auth account password, invitation policy role grant or schema migration was changed by these authority checks.
