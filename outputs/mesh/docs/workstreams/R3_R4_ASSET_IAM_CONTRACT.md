# R3–R4 cloud asset and IAM contract

Contract ID: `mesh.cloud-context`. Version: **1.0.0**. Identity algorithm: `mesh-cloud-identity-v1`. Date: **26 October 2026**.

Status: **shared implementation specification; documentation only**. The normalized DTOs and reader interfaces below are proposed interfaces, not deployed endpoints or existing database tables. R4 implements the producer/reader; R3 implements its consumer independently. This document does not implement either side, authorize new cloud access, change VADER, allocate a migration number, or certify effective AWS permissions.

## 1. Existing baseline and reuse

The shared starting point is MESH migration **0025**, with 55 application tables. Preserve these existing components:

| Existing component | Existing behavior | Contract use |
|---|---|---|
| `app.models.TenantRow` | UUID-string `id`, `organization_id`, timezone-aware `created_at` | Reuse for any new persisted tenant records; logical cloud keys below are separate from row UUIDs |
| `CloudAssessment` / `cloud_assessments` | Immutable tenant assessment with `provider`, `findings`, `partial`, nullable `errors`, `coverage`, `limitations`; inherited ID/time | Retained source assessment and immutable evidence anchor |
| `CloudAssessmentJob` | Tenant/request-key uniqueness; requester, leases/retries, scoped `assessment_id`; queued/running/completed/dead_letter/cancelled | Existing collection admission and job lifecycle; completion is not proof of complete inventory |
| `app.cloud.AWSAssessment` | Bounded read-only S3, EC2 security-group, RDS and limited IAM posture checks | Extend through R4 normalization; never infer a full graph from the current result |
| `configured_aws()` / `AWS_ROLE_BINDINGS` | Operator-controlled organization → assumed-role ARN binding, short-lived credentials and restricted collection session | Existing authority boundary; no tenant-supplied account/role may override it |
| `Principal`, `security.read`, `tenant_context`, `scoped`, `audit` | Application authorization, transaction-local database scope, scoped lookup and read audit conventions | Reuse at the reader boundary, including suspended/revoked authority handling |
| `EventContext`, `SecurityEvent`, `RiskAssessment` | Reported telemetry remains unverified; retained versioned risk evidence and explicit unknowns | R3 can reference normalized evidence; no automatic rewriting of existing events, incidents or scores |

Current collector limits include 200 guarded inventory entries, 50 paginator pages and a soft 60-second budget; findings are bounded to 1,000. Its configured-region limitation and missing groups/inline policies/SCPs/boundaries/resource-policy interactions are already documented. Current clients do **not** provide a retained, verified account/partition identity or a complete IAM permission inventory. R4 must collect/retain those explicitly for this contract.

Existing `CloudOutput` exposes only `id`, `provider`, `findings`, `partial`, `errors`, `coverage`, `limitations`. It does not expose collection times, AWS account, nodes, graph edges or effective decisions. `CloudAssessment.created_at` is persistence time, not an independently observed provider modification time. Do not silently repurpose these fields.

## 2. Tenant, provider and account identity

All normalized entities, edges, evidence references, queries and snapshot selections are scoped by **MESH `organization_id`**, a canonical UUID string. It is derived from authenticated/authorized context, never trusted merely because it appears in a payload.

`provider` is the literal `aws` in version 1.0. `partition` is one of `aws`, `aws-us-gov`, `aws-cn`. Unknown/unsupported partitions cannot produce verified normalized context. `provider_account_id` is a **12-digit string**, preserving leading zeros; never an integer, account alias, MESH organization UUID or role name.

The collection scope is:

```text
CloudScope = {
  organization_id: UUID,
  provider: "aws",
  partition: supported partition,
  provider_account_id: 12-digit string,  // account being collected
  service: service name or "account",  // e.g. iam, s3, ec2, rds
  scope_kind: "account" | "global" | "regional",
  region: string | null                // required for regional; null otherwise
}
```

R4 must verify the assumed session's identity using trusted provider evidence, such as STS `GetCallerIdentity`, and compare it with the authorized operator binding before publishing context. Record the binding revision/reference and verification evidence, without credentials. The existing binding is not a stored binding registry: a future registry UUID must not be fabricated for the current dictionary configuration. A nonsecret operator binding reference/revision is sufficient in v1.

An account mismatch is a failed collection with sanitized `account_mismatch` evidence; its results must not be published as belonging to the expected account. A resource ARN is a reference, not proof of tenant ownership. Empty ARN account/region components stay empty; scope supplies independently verified context where appropriate. Do not invent an account number for S3, AWS-managed policies or service principals.

MESH ownership means an authorized observation belongs to a MESH tenant; it does not imply that the tenant owns every referenced AWS principal/resource. References carry `ownership: "bound_account" | "external_account" | "aws_managed" | "aws_service" | "unknown"` and nullable `owner_account_id`. An external account is not automatically another MESH tenant. Cross-account references never authorize collecting that account or joining another organization's records.

If two organizations are explicitly authorized to observe the same AWS account, each has separate scoped keys/evidence. Never deduplicate or query across organizations based on account ID, ARN or display name.

## 3. Stable logical keys and lifecycle identity

### Key generation

Use `asset_key` for resource nodes and `principal_key` for principal nodes. These are deterministic **logical keys**, not replacement database primary keys. They fit the existing 100-character telemetry identifier bounds:

```text
identity = [
  "mesh-cloud-identity-v1", canonical_organization_uuid, "aws", partition,
  owner_namespace, service, region_or_empty, node_type,
  identity_kind, provider_identity
]
digest = lowercase SHA256 of UTF-8 JSON encoding of identity
asset_key     = "ca1_" + digest
principal_key = "cp1_" + digest
```

The JSON array has exactly the ordered string elements above. Serialize using RFC 8785 JSON Canonicalization Scheme (JCS), UTF-8 and no trailing newline; this fixes otherwise ambiguous JSON escaping across languages. No floats, null elements, Unicode normalization or display-name normalization participate. `owner_namespace` is the verified owner account ID, `aws-managed`, `aws-service`, or `unknown:<collected-account-id>` as applicable. The latter must retain unknown ownership; it is not verification.

`identity_kind` is `provider_uid`, `arn`, or `scoped_native_id`, in that preference order when reliable identity exists. Preserve provider UID and ARN casing/paths exactly. Provider identity is never a bare display name. Native IDs require account/partition/service/region/type scope. If neither a trusted UID, full provider reference nor a properly scoped native ID exists, return an unresolved reference rather than generating a name-only key.

`node_type` is a documented string such as `s3.bucket`, `ec2.security_group`, `rds.db_instance`, `iam.user`, `iam.role`, `sts.assumed_role_session`, `iam.account_root`, `aws.service_principal` or `iam.policy`. A role is a principal node; avoid creating a duplicate role asset with a different identity unless a future contract explicitly defines that representation.

Identity scope is fixed per type, not guessed from the collector endpoint:

| Types | Identity service / region |
|---|---|
| IAM users, roles, groups, policies, account root and AWS service-principal references | `iam` / empty region (global) |
| Assumed-role session | `sts` / empty region; retain its distinct evidenced session identity |
| S3 bucket | `s3` / empty region; a known bucket home region is a separate fact, not a key change |
| EC2 security group, RDS DB instance | `ec2` or `rds` / verified region required |

Other resource types require an explicit documented scope rule before publishing resolvable keys. Unknown required region/account identity produces unresolved evidence rather than a guessed global key.

### Reuse and reincarnation

- IAM user/role provider UIDs distinguish deleted/recreated principals even when the ARN/name is reused. Retain both UID and ARN when observed. STS session identity remains distinct from its backing IAM role; a session name is not a MESH user ID.
- ARN/native-ID fallback may identify a logical resource without proving lifecycle continuity. Carry `identity_strength: "provider_uid" | "scoped_reference"` and `incarnation_ref: string | null`. Do not assert that a reused bucket name/ARN is the same historical instance without supporting evidence.
- Discovering a stronger UID can produce a different key. Preserve earlier keys; expose a reviewed/evidenced alias mapping rather than silently retargeting historical incidents. A provider deletion/recreation produces a new incarnation, not a verified alias.
- All relationships and lookups also carry the organization and assessment scope. Prefix/hash appearance alone is never sufficient authorization or collision validation; retain and compare the canonical identity tuple internally.

`SecurityEvent.actor_id` is currently a reported string, not necessarily an IAM or MESH identity. R3 must use the resolver in section 8 and retain the original event. Do not replace existing actors/resources, truncate ARNs into `resource_id`, or equate an IAM username with an employee/email. Mapping to a MESH user needs explicit separately authorized evidence; otherwise it remains unknown.

## 4. Snapshot envelope and normalized records

R4 exposes one sealed immutable graph snapshot per retained `CloudAssessment`. `assessment_id` reuses that model's UUID; there is no independent graph ID requirement in v1. `source_job_id` is nullable for an existing synchronous collection, and when present must reference the same tenant and assessment. Snapshot publication must be atomic: readers cannot mix pages from different collections or observe a half-written graph. Once sealed, the assessment's normalized graph/normalizer version is fixed; a changed normalizer applies to a new collection/assessment, not a rewrite under an old ID. Multiple independently versioned graph snapshots for one assessment would require a separately agreed identity/version extension.

Required envelope fields:

| Field | Type / meaning |
|---|---|
| `contract`, `schema_version`, `identity_version` | `mesh.cloud-context`, `1.0.0`, `mesh-cloud-identity-v1` |
| `organization_id`, `assessment_id`, `source_job_id` | Tenant UUID, retained assessment UUID, nullable job UUID |
| `scope`, `requested_scopes` | Verified account envelope (`service=account`, `scope_kind=account`, `region=null`) and the explicitly requested service/region/check scopes |
| `binding_ref`, `binding_revision` | Nonsecret operator authority reference and immutable revision/digest |
| `normalizer_version`, `collector_version` | Exact producer versions retained with evidence |
| `publication_state` | `sealed`; running/failed/cancelled jobs are not sealed snapshots |
| `synthetic` | Strict boolean; production observations and synthetic fixtures never mix |
| `provenance` | `provider_observed` or `synthetic_fixture`; unnormalizable legacy input is reported by selection as unavailable, not a fabricated sealed graph |
| `collection_started_at`, `collection_finished_at`, `collected_at` | Aware UTC collection interval and receipt time |
| `coverage`, `partial`, `limits`, `errors`, `limitations` | Explicit scoped completeness, truncation and uncertainty |

A sealed snapshot may be partial. Its account envelope can contain global IAM/S3 observations and specifically declared regional EC2/RDS observations; every node and coverage entry retains its narrower scope. Declaring an account envelope does not claim collection of every service/region. Require `collection_started_at <= collection_finished_at <= collected_at`; child `observed_at <= child collected_at <= snapshot collected_at` when known. Provider observations are individually timed; this is not a claim of an atomic AWS-wide snapshot. Historic rows may remain unnormalized; do not manufacture missing identity, timing or coverage to make them satisfy the envelope. The producer assigns synthetic/provenance labels from trusted collection context; a caller's claim does not establish real provider observation.

### Asset record

Required fields: `organization_id`, `assessment_id`, `asset_key`, `node_type`, `scope`, `ownership`, `owner_account_id`, `identity_kind`, `identity_strength`, `provider_uid` (nullable), `arn` (nullable), `native_id` (nullable), `incarnation_ref` (nullable), `display_name` (nullable), `lifecycle_state`, `timestamps`, `facts`, `evidence_refs`.

`lifecycle_state` is `observed_present`, `observed_deleted`, or `unknown`. Missing from a partial inventory is **not** deleted. A deletion needs explicit provider deletion evidence or a documented complete comparable inventory comparison; retain that method and time. Account, service, region and identity/incarnation must match before comparing snapshots.

`facts` is an allowlisted map of typed observations, not arbitrary provider JSON. Each entry has `value` (primitive or null), `state: "known" | "unknown" | "not_applicable"`, `evidence_refs`, and an optional safe reason code. Null never means false. Examples include `storage_encrypted` and `reported_publicly_accessible`; a provider configuration flag does not prove end-to-end network reachability.

### Principal record

Same tenant/snapshot/scope/identity/timing/evidence fields, using `principal_key`, plus `principal_type: "iam_user" | "iam_role" | "assumed_role_session" | "account_root" | "federated_principal" | "service_principal" | "external_reference" | "unknown"`. IAM groups are asset nodes with `node_type=iam.group`, not authenticating principals; `member_of` points from the member principal to that group asset. Group membership and policy attachments are explicit relationships. Do not emit credential material, access-key IDs, session tokens or passwords. MFA/key-age summaries, if collected, are typed facts with provenance and unknown states, not authentication/session proof.

### Evidence reference

```text
EvidenceRef = {
  organization_id: UUID, assessment_id: UUID,
  evidence_id: UUID,              // proposed immutable normalized observation ID
  source_kind: "provider_response" | "policy_statement" | "legacy_finding" |
               "provider_audit_event" | "synthetic_fixture",
  operation: bounded operation/check identifier,
  observed_at: UTC timestamp | null,
  content_digest: lowercase SHA256 | null,
  verification: "provider_observed" | "reported_unverified" |
                "synthetic_fixture" | "legacy_unverified"
}
```

An evidence UUID must refer to an actually retained tenant-scoped observation; R4 owns its persistence design. A digest without retained evidence is not a resolvable reference. R3 stores bounded references/digests and the producer/contract versions in its own decision snapshots; later collection must not rescore or mutate old incidents automatically. Evidence retention must preserve referenced facts or report explicit expiry/unavailability, not silently point an old ID to a new observation.

## 5. IAM policies, permissions and relationships

Keep three concepts separate: **observed statements**, **evidenced relationships**, and **effective permission decisions**.

A permission observation contains the common tenant/assessment/timing/evidence fields plus:

- `permission_id` (retained UUID), `subject_ref: {kind: asset|principal, key}` (nullable only for an unresolved subject), `principal_key` (nullable; when present must agree with a principal subject), policy reference/ARN where applicable, `policy_version_ref` (nullable), and statement identifier or stable statement index/digest. Group/resource policy subjects use asset references.
- `policy_kind`: `identity_managed`, `identity_inline`, `resource`, `trust`, `permissions_boundary`, `session`, `scp`, `rcp`, `acl`, or `unknown`.
- `observed_effect`: `Allow` or `Deny`; unknown/unparseable statements are errors/unknown evidence, never default Allow.
- Exact bounded `actions`/`not_actions`, `resources`/`not_resources` and `condition_state: "absent" | "present" | "unknown"`, with a nullable condition digest/protected evidence reference. Preserve IAM matching semantics: do not expand a wildcard into verified per-resource grants or discard NotAction/NotResource/conditions.
- `evaluation_basis: "observed_statement_only"`, `effective_decision: "not_evaluated" | "unknown"`, and `unknown_dependencies` (policy layer/context identifiers).

Version 1.0 intentionally defines **no affirmative effective-access decision**. Current collection lacks the policy layers/context necessary for that claim. An attached AdministratorAccess policy is posture evidence, not proof of every effective action. A future authoritative request-specific evaluation interface requires an agreed version/capability with explicit principal/session, action, resource, context, policy versions and completeness; neither team may add an `allowed=true` shortcut.

Relationship records use an immutable `relationship_id` UUID, common tenant/assessment/timing/evidence fields, and:

```text
from: { kind: "asset" | "principal", key: scoped logical key }
to:   { kind: "asset" | "principal", key: scoped logical key }
relationship_type: bounded vocabulary below
basis: "provider_observed" | "policy_derived" | "reported_unverified" | "synthetic_fixture"
resolution: "resolved" | "external_reference" | "unresolved"
condition_state: "absent" | "present" | "unknown"
effective_decision: "not_evaluated" | "unknown"
```

Initial vocabulary: `member_of`, `policy_attached`, `trusts_principal`, `session_of_role`, `resource_policy_references`, `policy_may_allow`, `policy_explicit_deny`, `boundary_attached`, `network_group_attached`. A policy node uses an asset key with type `iam.policy`; both endpoints must resolve to nodes retained in the same tenant/snapshot, including explicitly marked external/unresolved reference nodes with a valid scoped provider reference. A wildcard such as `*` is a symbolic statement target, not an asset/principal identity: retain it in the permission observation and do not invent a keyed entity or access edge. Unsupported relationship types remain unknown to the consumer; never map them automatically to access.

| Relationship | `from` → `to` |
|---|---|
| `member_of` | IAM user principal → IAM group asset |
| `policy_attached` | Principal/group subject → policy asset |
| `trusts_principal` | Trusting role principal → referenced principal |
| `session_of_role` | Assumed-role session principal → backing role principal |
| `resource_policy_references` | Resource asset → principal referenced by its policy |
| `policy_may_allow`, `policy_explicit_deny` | Evidenced subject → concrete referenced resource asset; retain statement/condition references |
| `boundary_attached` | Principal → boundary policy asset |
| `network_group_attached` | Workload/database asset → security-group asset |

Only emit an edge supported by retained provider/statement evidence. The current collector does not collect every workload attachment; absence of an edge must not fill an unsupported scope with a negative fact.

`trusts_principal` points from the role containing the trust policy to the referenced principal. It is not a verified `can_assume_role` edge. `policy_explicit_deny` describes a statement, not an evaluated denial for arbitrary request context. Transitive traversal creates a **candidate** attack path only; trust, permission, condition and coverage gaps remain attached. A graph path never authorizes enforcement or proves an attack occurred.

Detailed IAM evaluation must account for the relevant identity/resource policies, session identity, conditions, permissions boundaries, organization controls and service behavior. R3 must not implement an approximate evaluator and label its output effective access. See the AWS references in section 12.

## 6. Time, freshness and historical selection

Use timezone-aware RFC3339 timestamps serialized in UTC (`Z`); reject naive input. Reuse `app.core.time.as_utc` and `app.models.now` in future implementation. Do not infer cloud time from local machine timezone.

Each normalized observation has:

| Timestamp | Meaning |
|---|---|
| `observed_at` | When R4 actually obtained the provider observation; nullable only when unknown/legacy |
| `provider_modified_at` | Provider-reported resource/policy modification time, nullable; never substituted for observation time |
| `collected_at` | When the collector received/normalized it |
| `fresh_until` | `observed_at + scope_max_age_seconds`, or null if observation time unknown |
| `max_age_seconds`, `freshness_policy_version` | Retained policy used for expiry; strict integer 1–86,400 seconds, default v1 3,600, configurable by R4 per scope |

At a supplied evaluation time, freshness is `fresh`, `stale`, or `unknown`. Fresh requires a known observation time at/before the evaluation time and expiry strictly after it. Provider clock anomalies, missing times or inconsistent collection intervals produce explicit uncertainty, not synthetic timestamps. Allow at most five minutes provider-time skew as a diagnostic tolerance; it does not make future-observed evidence available to historical evaluation.

`get_context(..., as_of=...)` defaults to knowledge available by that time: snapshot `collected_at <= as_of` and observation `observed_at <= as_of`. R3 may perform later retrospective analysis only with an explicit retained later knowledge cutoff; it must not silently leak future knowledge into an earlier decision. When specifying an assessment ID, use that immutable snapshot and report stale/partial context; never replace it silently with the latest snapshot. Default selection chooses the latest eligible sealed snapshot for the exact tenant/account/partition and synthetic mode whose declared `requested_scopes` include the requested service/region scope, ordered by `collected_at` then assessment UUID. Account-scoped queries match the account envelope; service/region queries require matching declared scope/coverage, not an assumption of account-wide collection. A newer denied/partial scope must remain visible; do not choose older complete data silently to hide it. Do not fall back to another account, region or organization.

Freshness is per observation/coverage scope. Fresh S3 data does not refresh stale IAM data. Completeness and freshness are independent: a complete old inventory may be stale; a fresh inventory may be denied/partial. Absence is evidence of no observed match only within the explicitly complete, fresh, applicable scope—not proof that the account is secure.

## 7. Coverage, uncertainty, empty results and limits

Each coverage entry identifies account/partition/service/region, the operation/check or policy layer, and `state: "complete" | "partial" | "denied" | "unsupported" | "not_requested" | "failed" | "unknown"`. Include observation/expiry times, observed count, nullable expected total, actual configured limit, `truncated`, and safe `reason_code`. Expected totals are never invented from returned counts.

Required IAM layer coverage is separately visible for users, roles, groups/membership, managed policy documents/versions, inline policies, trust policies, resource policies, boundaries, session policies, SCPs, RCPs and relevant ACL/service-specific controls. Version 1.0 can mark these unsupported/not_requested/unknown. The existing coarse `coverage: list[str]` only names attempted areas; it is **not** evidence that each listed area completed successfully.

`partial=true` if any requested/required snapshot scope is incomplete, errored or truncated; preserve an existing true legacy partial flag. Do not erase successful evidence because another scope failed. Conversely, partial success never yields global completeness. Staleness remains a separate freshness field. A completed job with zero findings may have unknown assets/IAM coverage. A complete empty inventory, a denied empty inventory and an uncollected scope are distinct results.

Initial safe reason vocabulary: `not_collected`, `legacy_metadata_missing`, `binding_missing`, `account_mismatch`, `access_denied`, `provider_unavailable`, `budget_exceeded`, `page_limit`, `unsupported_policy_layer`, `conditions_unresolved`, `identity_unresolved`, `clock_uncertain`, `stale`, `evidence_unavailable`. No raw provider exception, policy secret, token, request credential or unrestricted tags/documents appears in errors/logs.

R4 retains the existing collector limits until explicitly configured/reviewed. The normalized contract hard bounds are 10,000 nodes (assets + principals), 50,000 relationships, 10,000 permission observations, 1,000 findings and 1,000 error entries per snapshot. These are ceilings, not a promise the current collector supports that scale. Collections reaching any smaller configured limit report it. Page responses are at most 512 KiB; reject oversize records explicitly. Apply counts/byte limits before materializing/traversing all records. R3 applies its own analysis budget and records truncation/incomplete decisions rather than treating a sample as a complete graph.

Allowlist facts/metadata; no recursive arbitrary payloads or unbounded policy expansion. Bound node-type/service strings to 64 characters, ARNs to 2,048, provider UIDs/native IDs/display names to 256, facts to 32 entries per node, primitive fact strings to 256, and each statement's action/resource selector list to 1,000 strings of at most 2,048 characters. Over-limit input is incomplete/invalid evidence, never silently truncated into a complete permission observation. Do not emit credential values, access-key IDs, presigned URLs, unstructured session dumps or arbitrary claims/tags. Approved bounded principal/session identifiers may be retained as security metadata. IAM names/ARNs are sensitive security metadata: expose them only through authorized interfaces, not generic logs or external AI context. Full policy documents, when required, remain in R4-controlled protected evidence storage; this contract carries bounded summaries and references.

## 8. Consumer service boundary and existing APIs

### Existing implemented APIs — unchanged

All use the normal bearer identity, `X-Organization-ID` and `security.read` authorization:

- `POST /api/v1/vader/cloud/jobs` and GET job list/detail: request and observe bounded collection through existing job DTOs. Existing cancellation/retry routes remain unchanged. `request_key` stays tenant-scoped.
- `POST /api/v1/vader/cloud/assess`: existing synchronous posture collection.
- `GET /api/v1/vader/cloud/assessments` and `GET /api/v1/vader/cloud/assessments/{assessment_id}`: current retained posture DTOs, **not** normalized graph DTOs.

### Proposed R4-owned service interface — normative shape, not implemented

Implement a separate reader facade (suggested future module `app.cloud_context`) instead of making R3 query proposed R4 tables or call boto3 directly:

```text
get_context(db, principal, *, scope, as_of, assessment_id=None, synthetic=False)
    -> ContextSelection
list_assets(db, principal, *, assessment_id, limit=50, offset=0) -> Page[Asset]
list_principals(db, principal, *, assessment_id, limit=50, offset=0) -> Page[Principal]
list_permissions(db, principal, *, assessment_id, limit=50, offset=0)
    -> Page[PermissionObservation]
list_relationships(db, principal, *, assessment_id, limit=50, offset=0)
    -> Page[Relationship]
get_evidence(db, principal, *, assessment_id, evidence_id) -> EvidenceObservation
resolve_references(db, principal, *, assessment_id, references[<=100])
    -> ordered Resolution[]
```

`ContextSelection` contains `contract`, `schema_version`, the evaluated `as_of`/knowledge cutoff, `state: available|partial|stale|unavailable`, nullable snapshot envelope and safe reasons. If incomplete and stale, `state=stale` and the envelope still reports `partial=true`. Observation timestamps in pages remain immutable; R3 evaluates their freshness against this explicit cutoff rather than its changing local clock. Missing/legacy-only collection returns `unavailable` with an explicit reason; it does not return an empty complete graph. Reads do not initiate AWS collection or expose credentials. Unsupported storage/reader deployment returns `503` through the standard MESH error envelope, not made-up context.

Every page is pinned to tenant + assessment + contract version, ordered by logical key (relationship/permission UUID for those records), with `items`, `total`, `limit`, `offset`, `next_offset` (nullable). Reuse MESH bounds: limit 1–100, offset 0–100,000. Totals survive empty offset pages. Byte-limited pages may contain fewer than `limit` items; advance `next_offset` by the actual returned count, and never skip an oversized record silently. Counts describe retained records only; separate coverage describes missing inventory. Nodes/edges/permission observations outside the fixed snapshot must never appear midway through pagination. `EvidenceObservation` returns its `EvidenceRef`, `availability: available|expired|unavailable`, an allowlisted typed observation/statement summary or null, and safe reasons. It never exposes raw policy documents/credentials; permission fields use section 5. Retained-but-expired evidence returns explicit unavailable content; unknown/foreign IDs remain `404`. R3 must not depend on hidden raw policy storage.

A resolver input is a typed full ARN/provider UID/scoped native ID plus matching account/partition/region/type context—not an arbitrary actor string. Each result is `matched`, `ambiguous`, `not_found`, or `unknown`, with zero/one/bounded candidate keys and evidence/freshness. Only a unique evidenced match is matched; name similarity, wildcard overlap or cross-account ARN suffixes do not establish identity. Missing graph data is unknown, not a verified non-match. MESH-user resolution is outside this interface.

R3 may implement a local fake conforming to this interface while R4 is unfinished. Mark all such fixtures `synthetic=true` / `synthetic_fixture`; do not ship a fallback that passes them off as real context. A future HTTP adapter must preserve these DTOs/auth/errors and be separately registered/documented. **No new HTTP URL is promised by this document.**

## 9. Authorization, consistency and persistence rules

- Derive the tenant from a current authorized `Principal`; require `security.read` and active organization/membership at the boundary, with existing privileged-MFA policy in production. Background consumers require an explicitly authorized tenant service context; a caller-provided UUID is not a service credential.
- Set transaction-local tenant/user context; use restricted runtime credentials, forced RLS and composite organization/entity foreign keys for any new persisted objects. Never rely on a globally unique UUID alone to authorize a lookup. Missing/foreign assessment/evidence IDs return indistinguishable `404`, not foreign metadata or fallback context.
- Cache keys include tenant, pinned assessment, schema version, synthetic mode and requested scope; selection/freshness caching also includes the evaluation cutoff/policy. Recheck caller authority before serving cached data. Cached evidence never caches an authorization grant.
- Reader permission failure is `403`; malformed scope/version syntax/input is `422`; a well-formed unsupported major version or unsealed/incompatible requested snapshot is `409`; database/dependency failure is `503`. Use existing sanitized error/request-ID conventions. A well-formed authorized lookup with no collected snapshot returns structured unavailable context, not a fictitious successful assessment.
- Collection identity/account mismatch must fail publication. Provider operation failures are scoped coverage errors. Preserve current job lease/cancellation fencing and fresh requester checks; cancelled/obsolete attempts cannot publish the selected current snapshot.
- Record scoped read audits with existing conventions. Read access does not grant collection, role binding, account mutation, resource remediation or IAM enforcement authority. Credentials stay exclusively on the R4 collector boundary.
- Publish retained normalized evidence atomically and immutably with its assessment linkage. R4 chooses storage additions; R3 never changes `CloudAssessment.findings` or adds graph assumptions to `SecurityEvent.context` as an integration shortcut. Reuse existing assessment/job models and avoid a second collection queue.

## 10. Legacy compatibility and versioning

Preserve existing `CloudOutput`, assessment/job routes, findings (`rule`, `asset`, `severity`, `recommendation`) and coarse coverage/error arrays. A parallel normalized reader is additive. Existing `asset` labels such as a bucket name, group ID, username or `account-root` lack sufficient historical account/region/identity evidence on their own. Expose those as unresolved legacy findings with the original assessment ID; do not turn current operator bindings into fabricated historical ownership. Missing legacy timestamps/identity/coverage remain unknown; historical rows and incident decisions are not rewritten.

Use semantic contract versions independently of Alembic and collector versions. R3 declares supported major versions and required capabilities. Patch versions clarify/fix validation without changing meaning. Minor versions add optional fields/capabilities without making old records invalid; consumers ignore unknown optional output fields. Input validation may retain MESH's `extra=forbid` convention. New required fields, key algorithms, decision semantics, changed meanings/nullability or incompatible enum values require a new major version or an explicitly negotiated capability; never silently reinterpret an enum.

Unknown node/relationship types are preserved as unsupported/unknown and excluded from affirmative inference. An unsupported major version returns explicit incompatibility (`409`), never a fallback to name-based inference. Retain schema/identity/normalizer/collector versions in R3 decision evidence. Migrations through 0025 are frozen; coordinator approval/numbering is required for draft schema changes. This document assigns no 0026+ revision.

## 11. Independent implementation and acceptance checklist

R4 owns collection, verified account binding, normalization, immutable snapshots/evidence, coverage/freshness computation and the reader facade. R3 owns bounded resolution/traversal, candidate attack-chain logic and retained analysis decisions. R3 must not require raw boto3 clients, database table layouts, credential files, AWS mutation permissions or a live account to run its synthetic contract tests.

Before merging, both sides must share contract fixtures covering:

1. Same ARN/native ID in different tenants, accounts, partitions and regions; keys remain scoped. Known IAM UID versus reused name/ARN; sessions versus roles; unresolved external/service references.
2. Allowed/denied/missing inventory and policy layers; complete empty inventory versus unknown empty data; bounded/truncated inventory; conditional/wildcard/NotAction statements without effective-access claims.
3. Fresh, stale and missing/skewed timestamps; as-of selection without future evidence; pages pinned to a single sealed snapshot; cancellation/obsolete-worker publication rejected.
4. Cross-tenant reader/FK denial, revoked/suspended authorization, secret-free serialization/logging and bounded resolution/traversal.
5. Legacy posture-only rows, unsupported major versions/types, missing evidence and synthetic isolation. Existing API/RLS/risk tests continue passing; no retroactive incident rescoring or automatic enforcement.

Documentation-only acceptance for this task: the producer/consumer boundary is defined, existing-versus-proposed behavior is explicit, and no runtime, VADER, migration or live cloud configuration changes are made. A future implementation is not complete merely because fixtures pass; actual provider evidence requires separately authorized configuration.

## 12. References

Local sources: `backend/app/cloud.py`, `cloud_worker.py`, `cloud_jobs.py`, `models.py`, `intelligence_api.py`, `telemetry_schema.py`, `risk_engine.py`, `core/config.py`, `core/time.py`, and `docs/RISK_ENGINE.md`.

Primary references: [GetCallerIdentity account/principal identity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html), [policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html), [request evaluation and policy layers](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-denyallow.html), [principal references and role recreation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html), and [RFC 8785 canonical JSON](https://www.rfc-editor.org/rfc/rfc8785).
