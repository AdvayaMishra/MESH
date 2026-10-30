# R4 normalized cloud context implementation — revision 0026

Current R4 delivery: see [R4 status](R4_STATUS.md) for AWS-optional setup/status APIs, development samples and verified handoff scope. The implementation details and earlier checkpoints below remain valid within their stated scope. Real AWS acceptance remains deferred/unverified until connected.

Collector follow-up: see [IAM/S3/billing implementation](R4_IAM_BILLING_FOLLOWUP.md) for the newer normalizer2 behavior and current validation. The detailed collector scope and test counts below describe the earlier normalizer1 checkpoint.

This companion records implemented behavior for `R3_R4_ASSET_IAM_CONTRACT.md` version 1.0.0. That contract remains the shared specification. R3 consumes the facade below; it does not need to query the storage column or modify VADER to use the fixture independently.

## Implemented boundary

`app.cloud_context` now implements `get_context`, `list_assets`, `list_principals`, `list_permissions`, `list_relationships`, `get_evidence` and `resolve_references`. These are internal Python services, not new HTTP endpoints. The existing assessment and job HTTP APIs retain their response shapes. Existing API authentication constructs the request principal with its verified assurance, session expiry and issue time; the reader additionally refreshes membership/organization status and checks session revocation/expiry before every read.

Example for an already authenticated, request-scoped `principal` and database session:

```python
from datetime import UTC, datetime
from app.cloud_context import get_context, list_principals
from app.cloud_context_schema import Scope

scope = Scope(
    organization_id=principal.organization_id,
    provider="aws", partition="aws", provider_account_id="012345678901",
    service="iam", scope_kind="global", region=None,
)
selection = get_context(db, principal, scope=scope, as_of=datetime.now(UTC))
if selection.envelope is not None:
    page = list_principals(db, principal,
                          assessment_id=selection.envelope.assessment_id)
```

A bare principal UUID is not a service credential. Production callers must come through the authenticated MESH boundary with an active tracked session and required MFA. A future machine identity needs a separately authorized service boundary; no bypass is introduced here. Reads never call AWS, change role bindings, initiate collection, mutate incidents or grant enforcement permission.

Selection uses exact organization/account/partition/synthetic mode and declared service/region scope. It retains the supplied UTC knowledge cutoff, selects the newest eligible sealed snapshot, preserves newer partial evidence, and reports stale/partial/unavailable explicitly. Selection scans at most 1,000 candidate assessments for an account; exceeding that bound fails with 503 rather than returning an older misleading result. Pinned reads never switch assessments. Legacy posture-only rows remain unnormalized and return explicit unavailable context.

Pages are sorted and pinned, keep totals on empty offset pages and enforce strict limit 1–100/offset 0–100,000. A 512 KiB response bound can shorten a page; `next_offset` advances by the returned count. An oversized first record fails explicitly. Snapshot storage is capped at 8 MiB in addition to record/count bounds. The reader checks stored size before materializing JSON. Large-scale indexing/sharded evidence storage is not claimed.

Resolver matching is exact across declared scope/type and retained ARN/UID/native identifier. Unique available evidence is required for `matched`; ambiguity or missing/expired evidence stays explicit. `not_found` is only emitted within a complete matching inventory scope. IAM's combined inventory remains partial because required policy layers are uncollected. Resolution establishes identifier correspondence; R3 must evaluate retained observation times against its explicit cutoff and must not interpret a match as effective access or observed attack activity.

## Collection and storage

The operator-bound AWS session is independently verified before inventory client creation. The existing collector now retains bounded S3 bucket, regional EC2 security-group, regional RDS instance, IAM user/role and observed managed user-policy attachment records. Available IAM provider UIDs distinguish recreated users/roles; ARN/native fallbacks remain scoped references. RDS exposure/encryption fields are typed observations, not claims of end-to-end reachability. Missing regional identity produces unresolved evidence, never a guessed global resource.

Role trust statement selectors/effect/condition presence and digest are retained as `observed_statement_only` permissions. Raw conditions, principal documents, credentials, access-key IDs, arbitrary tags and full provider responses are excluded. Trust principal selectors are currently an unknown dependency; this producer does not emit `trusts_principal` or verified assume-role edges. Evidence digests describe the retained allowlisted summary, not a digest of an unavailable full AWS response. Managed user-policy attachment edges do not imply that the attached policy document was fetched or permissions evaluated.

Every normalized result remains partial while groups/membership, managed policy documents, inline policies, resource-policy interactions, boundaries, session policies, SCPs, RCPs and ACL/service controls are uncollected. Their coverage entries are explicit `unsupported`. Root/MFA/key-age posture findings continue to work through existing legacy findings; they are not silently promoted into a complete normalized IAM graph.

A nullable `CloudAssessment.normalized_context` JSON column reuses the existing immutable assessment ID and forced tenant RLS. The normalized envelope and records/evidence are inserted atomically. The existing append-only trigger protects the column. Database checks bind the envelope to its assessment/organization and bound its size; a deferred constraint trigger checks a worker snapshot's source job against the same tenant, assessment and completed status at commit. Existing lease fencing and requester rechecks still govern worker publication. The synchronous path uses the same validated publisher. No historic rows are rewritten or backfilled with current bindings.

Coordinator-assigned additive migration: `0026_cloud_context.py`; frozen SQL: `20261026000300_cloud_context.sql`. Migrations through 0025 remain unchanged. This migration also removes inherited cloud-assessment grants from Supabase API roles, including `service_role`, grants only SELECT/INSERT to `mesh_runtime`, and revokes access to the new trigger function. Application table count stays 55. The old 0025 ZIP is not a current source bundle for this checkpoint.

## Configuration and remaining R4 work

Configure `AWS_ROLE_BINDINGS` as the existing operator-controlled organization UUID → IAM role ARN mapping, an AWS source credential chain allowed to assume that role, the configured AWS region and the role trust/read-only policy. Do not paste credentials into chat or repository files. `configured_aws` uses 900-second sessions and its existing restricted read-only session policy. Missing binding, malformed/mismatched account/session or provider failure fails closed; there is no fixture fallback.

Live AWS collection is not verified here. R4 still needs expanded IAM and relevant resource-policy collection, reviewed graph/reference semantics for external/service principals and trust targets, authorized real account fixtures, a separately authorized billing adapter, and production operational/load acceptance. This checkpoint does not establish full effective-permission evaluation, VADER integration or production security clearance.

The explicitly synthetic sharing fixture is `fixtures/cloud-context-v1.synthetic.json`. It is schema-validated, contains no real cloud observation and uses a fixed knowledge time of 2026-10-26T00:00:00Z (expiry one hour later). R3 should preserve `synthetic=true` and `synthetic_fixture` provenance when using it. Do not use it as a production fallback. Hosted/runtime and local evidence reports are listed in `IMPLEMENTATION_STATUS.md`; test results do not imply live AWS success.

## Verified checkpoint evidence

- Windows backend suite: 835 passed, 25 skipped; `docs/cloud-context-local-test-results.xml`.
- Native PostgreSQL: 23 actual integration cases, fresh 24-artifact frozen SQL application, dump/restore equivalence and cleanup; `docs/postgres-native-results.json` and `docs/supabase-frozen-sql-local-results.json`.
- Hosted Supabase 0026: additive migration/ACL checks and five protected-runtime checks, zero metadata differences, all fixture rows rolled back; `docs/supabase-cloud-context-results.json` and `docs/supabase-cloud-context-workflow-results.json`.
- Current source/image Compose: ten gates pass, Linux 858 passed/2 skipped including 23 actual PostgreSQL cases, restore revision 0026 and project cleanup; `docs/docker-runtime-results.json`, `docs/linux-test-results.json` and `docs/compose-backup-restore-results.json`.
- Ruff/format, mypy84 and Bandit pass. Runtime artifact checks verify 41 pins, UID10001 and absent build tools. These are not independent security review.
- The backend OS gate still fails on 69 advisory references across 61 source packages. The refreshed official Debian review retains all findings; production clearance remains false. VM stopped after acceptance; test disk/cache retained. The previous ZIP has not been regenerated.
