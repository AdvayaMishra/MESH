# R4 IAM, resource policies and billing adapter follow-up

Current R4 delivery: see [R4 status](R4_STATUS.md) for AWS-optional setup/status APIs, development samples and verified handoff scope. The implementation details and earlier checkpoints below remain valid within their stated scope. Real AWS acceptance remains deferred/unverified until connected.

Subsequent completion: durable billing admission/storage/worker/API are implemented in0027; see [billing workflow contract](R4_BILLING_COLLECTIONS.md). The adapter-only remaining-work notes below describe the earlier0026 checkpoint. The current principal/root-fact additions are described next; older validation totals remain historical.

## Current principal and root-fact additions

Normalizer `mesh-aws-normalizer-3` preserves shared contract `mesh.cloud-context` 1.0.0 and its existing identity-key rules. A twelve-digit account principal and its equivalent partition-bound IAM root ARN resolve to the same account delegation reference. This does not prove a root-user login or effective access. Exact STS assumed-role session ARNs use the already documented `sts.assumed_role_session` type and a separate STS scope/key. References retain unknown lifecycle and scoped-reference identity; no observed session activity or `session_of_role` relationship is invented. Wrong-partition, wildcard and malformed session references remain incomplete. Federated principals and other unsupported namespaces remain unknown. See [AWS principal semantics](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html).

Actual IAM account-summary reads now retain the contract's typed root console, MFA and access-key-presence facts with `iam.account_summary` provenance and the verified account/partition. No credential IDs are retained. These facts are distinct from reference-only account nodes. IAM and reference-only STS inventory retain partial coverage. Required regional coverage explicitly checks S3/IAM/EC2/RDS membership, so an added STS scope cannot conceal a missing regional service. Historical snapshots are immutable and keep their original normalizer version.

Backend-only changes following the verified 0026 cloud context checkpoint. No new schema, frontend or VADER consumer changes. The shared cloud-context contract remains 1.0.0; the existing documented AWS service-principal type now has key support. Normalizer version is `mesh-aws-normalizer-2`. Historical snapshots remain immutable.

## Implemented collection

- AWS `GetAccountAuthorizationDetails`, filtered to users/roles/groups, in pages of at most 50 and at most 50 pages. It shares the existing 200-entry/soft-60-second inventory budget, so partial collection is expected on larger accounts. No limit was silently raised.
- Provider UID-backed IAM groups, users and roles; exact group membership resolved across collected pages. A missing group is unknown, never a name-only fabricated group.
- Inline policy documents; attached managed policy profiles and exact default versions (cached only within one collection); boundary attachments and observed statements. A version change, denial or malformed document stays incomplete. No automatic fallback to an unverified policy version.
- Exact Action/NotAction and Resource/NotResource observations, Allow/Deny, condition presence/digest and policy version references. Raw JSON and RFC3986-encoded JSON are distinguished so percent literals are preserved. Policy bytes, structure, selectors and statements are bounded before retention. No full policy documents, raw condition values or arbitrary tags are exposed through the normalized facade.
- Role trust references point from the trusting role to exact collected principals or explicitly unknown external/service references. An existing unique collected ARN uses its retained UID-backed key. Referenced-only nodes have unknown lifecycle and scoped-reference identity; they do not claim that the referenced entity was independently inventoried. Wildcards and NotPrincipal do not create fake nodes or verified access edges. Ambiguous references remain incomplete. Numeric account shorthand/federated principal types and some service namespaces remain unsupported rather than guessed.
- S3 bucket resource-policy statements and exact principal references, with absence (`NoSuchBucketPolicy`) distinct from denial/deleted bucket. Failed bucket inventory prevents complete resource-policy coverage. Other services' resource policies, organization SCP/RCP, session policies and ACL controls remain unsupported. Full effective permissions are not evaluated.

`AWS_ROLE_BINDINGS` remains operator-controlled. The restricted posture session now additionally permits `iam:GetAccountAuthorizationDetails`, `iam:GetPolicy`, `iam:GetPolicyVersion` and `s3:GetBucketPolicy`; source-role policy/trust must independently permit these reads. Read-only session policies do not grant permissions that the role lacks. No real AWS access is asserted by synthetic SDK tests.

## Billing adapter

`app.aws_billing.configured_billing(organization_id)` is reached through `live_billing_adapter("aws", organization_id=...)`. It requires a separate `AWS_BILLING_ROLE_BINDINGS` organization-to-role mapping. Posture roles are not reused implicitly. It verifies the assumed session/account before constructing a Cost Explorer client, uses only `ce:GetCostAndUsage`, and fixes the query to the verified linked account, monthly SERVICE groups and UnblendedCost. Commercial AWS only; unsupported partitions fail closed. Source credentials, role trust, billing permissions and Cost Explorer activation must be configured by the operator. Requests can incur AWS API charges; no live request was made here.

The adapter accepts the current twelve calendar months, has ten-page/1,000-group/response/report byte bounds and a soft time budget with SDK timeouts. It retains exact signed decimals (including refunds), estimated status and separate totals for each currency. It never aggregates incomparable usage units or treats observations as verified invoices. Provider failure, duplicate groups, changed periods, malformed amounts or invalid/repeated tokens return sanitized unavailability, not a partial successful financial total.

`AWSBillingReport` is separate from the earlier nonnegative `BillingBatch` fixture model: refunds cannot be squeezed into a nonnegative manual cost row or rounded silently. This internal adapter is **not yet** a persisted billing ingestion workflow. Remaining work: durable collection admission/results, fresh finance authorization, idempotency/leases/retry fencing, API response contracts and operational acceptance. Existing finance totals are unchanged; no automatic posting or double-counting is introduced.

## Validation

New synthetic SDK tests exercise pagination, grouping, membership, managed-version drift, denied/partial coverage, trust references, secret exclusion, calendar bounds, exact refunds/currencies and credential mismatch. Final full-suite and current-image results are recorded in IMPLEMENTATION_STATUS.md when complete. No hosted migration was needed. Existing 0026 live database evidence remains separately scoped; no live IAM, resource policy or billing provider success is fabricated.

Primary API references: [IAM authorization details](https://docs.aws.amazon.com/boto3/latest/reference/services/iam/client/get_account_authorization_details.html), [Cost Explorer GetCostAndUsage](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html), [exclusive billing date intervals](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_DateInterval.html).

Current checkpoint: Windows878/25, Linux901/2,23 actual PostgreSQL cases,ten Compose gates and restore0026 pass. Static checks pass across88 app modules. Runtime artifact/source fingerprints match; backend OS gate still fails69 advisory references. No live AWS calls and no new hosted migration.
