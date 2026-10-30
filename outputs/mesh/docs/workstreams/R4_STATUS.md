# R4 cloud and billing backend delivery

Scope clarified 27 October 2026: MESH operates without an AWS account. R4 delivers implemented adapters, safe unconfigured behaviour, explicit development samples and documented authorized live setup. Real AWS account connection/acceptance remains unverified until an account is connected. This is not production clearance or a claim that real AWS checks succeeded.

## Delivered backend

- Read-only AWS posture adapter with operator-bound account/role, verified STS session/account and tenant ExternalId, bounded S3/EC2/RDS/IAM collection and explicit partial/denied/unknown coverage.
- IAM users/roles/groups, policy versions/statements, boundaries, memberships, trust/account/service/session references and S3 resource-policy observations. Unsupported effective-permission layers remain unknown.
- Durable assessment jobs/worker, retries/leases/cancellation, retained normalized context/evidence and version1.0.0 R3 reader facade. No R3 detection/correlation consumer code is added.
- Separate-binding Cost Explorer adapter, exact signed/currency-separated reports, durable finance-authorized admission/history/cancel/report APIs and worker, actor/period replay and paid-dispatch fencing.
- Local setup status, development sample billing, unconfigured job admission/retry rejection and fresh job authority. Cloud request replay is actor/provider-bound; existing jobs can replay after binding removal, but new work cannot be admitted.
- Restricted role template, tenant-external-ID trust conditions, configuration guides and local/hosted tests. No AWS resource deployment or provider request was performed.

## New API contracts

Normal bearer identity, tenant header and fresh membership/session/MFA checks apply. No account ID, role ARN, credential source or secret is exposed; status/sample reads never resolve SDK credentials or probe AWS.

| Route | Permission | Result |
|---|---|---|
| GET `/api/v1/cloud-integrations/aws/posture/status` | security.read (security analyst) | Local posture binding status |
| GET `/api/v1/cloud-integrations/aws/billing/status` | finance.read (owner) | Local billing binding status/sample availability |
| GET `/api/v1/cloud-integrations/aws/billing/sample?period=2026-10` | finance.read; development only | Explicit sample, outside actual billing history/finance |

Status states: `not_configured`, `configured_unverified`, `invalid_configuration`. Reasons: `role_binding_missing`, `role_binding_invalid`, `partition_unsupported`, or null. `provider_check=not_performed` and `provider_requests_performed=false` prevent a role-shaped binding being mistaken for verified credentials/trust/permissions. Posture retains supported AWS partitions; billing remains commercial AWS only.

Samples have `data_source=sample`, `synthetic=true`, `provider_verified=false`, `invoice_verified=false`, `affects_recorded_totals=false`, and an existing BillingBatch with `provenance=fixture`. Three illustrative rows total USD155.50 and EUR10.00 separately; hours/GiB-months/requests stay separate. The period is illustrative; generated_at is response time, not a provider observation timestamp. No fake provider account is invented. Reads add access audits only, never CostRecord/BillingCollection/job rows. No live failure automatically falls back to samples. Outside development the endpoint returns503 and sample_available=false.

Missing/invalid posture bindings reject new admission/retry with503 before enqueueing. Existing live billing admission also fails closed. Normal reports/history never include sample values. Owner does not inherit raw security access; analysts/HR do not inherit finance access. The existing five durable billing routes and cloud-context contract remain compatible; unconfigured cloud jobs now fail early rather than entering a doomed retry queue.

## Completion boundary

| R4 milestone | Backend/local delivery | Account-dependent acceptance |
|---|---|---|
| R4-01 access setup | Role template, fixed bindings, validation/status, least-privilege session policy and guide implemented | Actual account/workload identity/target-role setup is unconfigured; no deployment claimed |
| R4-02 inventory/IAM | Collectors, context, jobs, isolation/failure/coverage tests and reader facade implemented | Real inventory comparison and correct/omitted/wrong ExternalId verification deferred until connected |
| R4-03 billing | Adapter, durable workflow, finance guards and explicit samples implemented | Real Cost Explorer feed/account/period/currency/refund/outage/replay comparison deferred until connected |

The backend/local handoff is complete following current-image acceptance; the last column must never be relabelled as passed. Those checks are not prerequisites to using the rest of MESH. See [role setup](../../infrastructure/aws/README.md), [billing contract](R4_BILLING_COLLECTIONS.md), and [shared R3/R4 contract](R3_R4_ASSET_IAM_CONTRACT.md).

## Verification

Windows: **1,040 passed / 32 skipped**. Native PostgreSQL: **30 actual cases passed**. Static checks and mypy over 95 application modules pass. The new PostgreSQL case exercises sample provenance, no finance writes, audit and revoked-owner denial. Six hosted Supabase checks pass with all synthetic organization/member/session/audit rows rolled back; no AWS calls, customer rows or Storage changes. No schema migration: deployed revision 0028, 57 forced-RLS tables and 26 frozen SQL artifacts remain unchanged. Final source/image acceptance passes1070 Linux tests/2skips including30 actual PostgreSQL cases and all ten Compose gates. Exact fingerprint/image and scope are recorded in r4-delivery-checkpoint.json. The R4 backend/local delivery is complete; real AWS acceptance remains deferred/unverified until connected.

Production clearance stays false; OS/native review, release operations and the other workstreams remain separate. No frontend was created, modified or integrated.
