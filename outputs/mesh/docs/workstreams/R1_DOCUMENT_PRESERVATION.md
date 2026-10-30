# R1 identity document preservation

Backend implementation at revision 0028. These controls preserve retained identity evidence during an independently reviewed hold. They do not choose a legal basis or jurisdictional retention period. Production privacy approval and real document/OCR operational acceptance remain separate.

## API contract

All routes require a verified identity, `X-Organization-ID`, active HR membership and privileged MFA when enabled. Owner, developer and analyst roles do not inherit this access. State changes recheck current HR authority, organization status, session expiry/revocation and membership access cutoff after acquiring the tenant lock.

The same fresh checks now apply to signed-link reads, OCR-result reads, human decisions, OCR retry/manual review and API-triggered expiry, as well as hold/queue operations. Cached organization status is refreshed after waiting for the tenant lock. Uploads repeat the membership/session/organization check after malware/image validation, then lock and refresh employee ownership and employment status before staging a reference or contacting Storage. Offboarded/reassigned employees cannot complete an upload using an earlier authorization check. The maintenance worker still performs retention for suspended tenants and honors holds; it does not obtain HR content access through that maintenance path.

| Method and route | Request | Result |
|---|---|---|
| GET `/api/v1/hr/identity-documents` | `limit`, `offset`, optional `employee_id`; `status`: `pending_hr` (default), `approved`, `rejected`, `deleted`, `all`; `include_expired=false` by default | Metadata-only review queue with `items`, `limit`, `offset`, `has_more` |
| POST `/api/v1/hr/identity-documents/{document_id}/holds` | `request_key` UUID; `reason_code`: `dispute`, `investigation`, `regulatory`, `other` | 201 with hold metadata; an exact actor/document/reason replay returns the same record |
| GET `/api/v1/hr/identity-documents/{document_id}/holds` | `limit` and `offset`, using existing bounded pagination | Audited hold history ordered by creation descending and ID; metadata only |
| POST `/api/v1/hr/identity-document-holds/{hold_id}/release` | `reason_code`: `resolved`, `entered_in_error`, `other` | 200 with independently released metadata; exact reviewer/reason replay is idempotent |

Hold output includes ID, document ID, classification, placing reviewer/time and releasing reviewer/time/classification. It excludes object paths, bytes, OCR ciphertext, raw personal data and request credentials. Unknown input fields are rejected. Free-text investigation details belong in an authorized case-management process, not these preservation records.

Queue items include document/employee IDs, media type, review/OCR status, creation/expiry time, `expired` and `active_hold`. The query selects only these metadata columns; it does not load OCR ciphertext, storage keys or digests. Default results contain unexpired pending reviews. History filters never grant content access. An employee filter must resolve inside the selected tenant. Ordering is creation descending then ID; pagination uses existing bounded offset semantics, and concurrent inserts can move page boundaries. Queue access is audited. A hold does not block ordinary independent HR review of an unexpired document, but does suspend automated OCR processing.

Only one active hold per document is allowed. A request key remains bound to its original actor, document and reason after release; replay never reactivates it. A new hold needs a new request key. Deleted documents cannot acquire new holds. The employee cannot place or release their own document's hold. Release requires an active HR reviewer different from the placing reviewer. Suspended organizations cannot place/release holds; retention continues for suspended organizations and still honors existing holds.

Errors follow existing API conventions: 401 stale/missing session; 403 insufficient current authority; 404 cross-tenant or unknown reference; 409 self-review, existing active hold, conflicting replay or release; 410 deleted document; 422 invalid input; sanitized service errors for unavailable dependencies.

## Preservation and processing

Retention excludes active holds, selects at most 50 expired records per cycle and holds the same tenant/document locks used by hold changes. PostgreSQL trigger admission also locks the referenced document. Concurrent preservation and retention are tested using independent sessions. A database partial unique index prevents duplicate active holds. Composite foreign keys bind the document and both reviewers to the same organization.

Holding a document does not change its expiry. Existing signed-URL and OCR-result endpoints continue returning 410 after expiry. The hold creates no extra content-access route and does not extend any already-issued signed URL. An unexpired document retains its existing HR-only access policy. Orphan reconciliation preserves every durable document reference, including held records.

Placement cancels queued/running OCR and clears its lease without erasing existing encrypted evidence. In-flight worker publication is fenced by the changed status/lease. OCR retry and manual-clear operations reject held documents. PostgreSQL guards prevent changing held object identity, digest, expiry or OCR ciphertext, and prevent marking/deleting the held record. Hold admission/history are immutable except one complete, independent release. The releasing review does not renew document access or queue OCR automatically. Normal expiry can delete the bytes and clear OCR after release; an unexpired cancelled OCR job requires an explicit authorized retry.

`document_holds` uses forced tenant RLS. Direct Supabase API roles have no table/function access; the backend runtime has SELECT/INSERT/UPDATE and no DELETE. Audit actions record placement, release and history access using opaque record IDs. Retention preserves holds even for suspended tenants. No customer identity document was collected or deleted while implementing this feature.

These controls govern MESH operations. They cannot reconstruct objects deleted before placement, prevent independent Storage administrator actions, or make external Storage deletion transactional with PostgreSQL. Storage administrator access, backup handling, key retention/rotation, legal basis and held-record disclosure require production operator review. A database hold is not proof that bytes independently exist at the provider.

All private object operations reject malformed/noncanonical UUID paths before provider access. Signed links, retention deletion and OCR additionally require the stored path to equal the record's exact organization/employee/document identity. A corrupted row pointing at another tenant, employee or document fails closed with a sanitized error. OCR checks the binding both before dispatch and before publication, including digest changes during processing. No mismatched path is signed, deleted or used for a new OCR request; an in-flight result is discarded if its reference changes. This service validation is additional to tenant RLS and does not rewrite existing object references.

## Deployment and evidence

Additive Alembic revision `0028_document_holds.py` and matching Supabase SQL `20261026000500_document_holds.sql` are applied to the existing project. Earlier migrations are unchanged. The deployed migration is frozen; corrections require a new additive revision. Fresh native PostgreSQL applies all 26 frozen SQL artifacts and restores revision 0028 with 57 forced-RLS tables.

See `supabase-document-holds-migration-results.json`, `supabase-document-holds-workflow-results.json`, `document-holds-local-test-results.xml`, `postgres-native-results.json` and current implementation status. Rollback-only hosted fixtures do not create Storage objects or call identity, mail, OCR or cloud providers. Exact current-image Compose/Linux acceptance is recorded separately.
