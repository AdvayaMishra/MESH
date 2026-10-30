# R1/R4 provider response acceptance bounds

Backend-only hardening after deployed schema 0028. No API/model/migration, frontend or VADER change.

## Private Storage

Every Storage request sends `Accept-Encoding: identity`. Encoded responses are rejected before application payload iteration; the adapter does not accept compressed input that can expand beyond its byte budget. If present, Content-Length must be one bounded ASCII decimal within 2 MiB and must match the received payload. The actual body remains bounded independently of that declaration, with the size checked before extending the retained buffer.

GET requires status 200; DELETE accepts 200/204; POST accepts 200/201. Async 202 and partial 206 do not count as a completed operation. Malformed, oversized, truncated, encoded, unexpected-status or late responses become the existing sanitized 503, with the response stream closed. No partial bytes/result or raw provider diagnostics are returned.

An elapsed 20-second acceptance budget is checked after response headers, on each delivered body chunk, after the body and after JSON decoding. The previous fixed 16-KiB iteration coalescing is removed so small arriving chunks trigger the budget checks. Existing 15-second transport timeouts remain. This is a soft acceptance deadline checked around blocking transport/decoding, not a hard interrupt: a blocking read can run until its transport timeout, and rejection cannot recall an already-dispatched provider mutation. An unconfirmed upload may leave an orphan for the existing tenant-scoped reconciliation protocol; an unconfirmed deletion is not marked as successful in the database. The adapter introduces no automatic retries.

Canonical object paths, exact tenant/employee/document binding, verified TLS, backend-only API keys, private bucket policies, signed-link validation and malware/image gates remain in force.

## AWS billing

The existing 60-second collection budget is now checked immediately after each provider response, during group processing, before aggregate/report construction and after final validation/serialization. A late final page or late local processing cannot return a successful financial report merely because no next page is requested. The SDK transport timeouts and disabled billing retries remain unchanged; this also is a soft acceptance deadline, not provider cancellation.

Late or incomplete results use the existing sanitized unavailable/incomplete error. Durable billing dispatch remains recorded, no successful report is published, and no automatic repeat is introduced. A provider may still charge for a dispatched query even when the response is discarded; failure is not a claim of zero charges. Exact signed decimal/currency/account/period provenance checks remain unchanged.

## Real Storage acceptance

The configured Supabase Storage service passed seven controlled checks with one fictional 8x8 PNG under a newly generated random UUID namespace: empty owned prefix, bounded upload, exact private download, metadata inventory, signed-link download, anonymous public-read denial and exact-object cleanup verification. No customer document, database row, bucket policy, Auth account or mail/SCIM/cloud configuration changed. No key or signed URL was recorded. Evidence: `storage-response-bounds-live-results.json`.

This proves the current Storage protocol accepts legitimate provider responses with these bounds and preserves the tested public-read denial. It does not establish real employee identity verification, OCR accuracy, production privacy decisions, mail/Auth/SCIM/AWS acceptance or throughput. Fault injection is local: synthetic streams test malformed metadata, compressed/async/partial responses, trickling bodies and late billing stages. Full regression/image results are recorded in implementation status and `provider-response-bounds-checkpoint.json` when complete.
