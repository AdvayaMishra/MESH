# R4 cloud identity implementation checkpoint — 26 October 2026

This checkpoint continues R4 without changing VADER/R3 code or frontend code. It implements foundations of the shared `mesh.cloud-context` 1.0.0 contract, not its entire producer/reader interface.

## Implemented

- `app.cloud_identity.AWSAccountIdentity` parses the operator-bound IAM role and preserves the twelve-digit account as a string, including leading zeroes. Commercial, China and GovCloud partitions are supported.
- `configured_aws` queries `GetCallerIdentity` using the newly assumed credentials. Account, partition, role/session ARN and assumed principal ID must agree with the operator binding and `AssumeRole` response before S3, EC2, RDS or IAM inventory clients are created. Mismatches and provider failures return the existing sanitized 503 response. An unbound tenant makes no AWS request.
- IAM role paths are handled without equating an IAM role ARN with an STS session ARN. The verified identity remains internal collector metadata; it is not represented as a persisted graph or newly exposed API field.
- `app.cloud_keys.cloud_node_key` implements canonical string-array hashing for supported contract node types. Keys include canonical organization UUID, partition, ownership namespace, service, region, node type, identity kind and provider identity. Type-specific global/regional rules, ARN account/region/type matching, bounds and invalid Unicode rejection fail closed. Provider casing and paths are preserved; changed IAM provider UIDs produce different keys.
- These helpers do not infer effective permissions, authorize another account, or establish provider existence. Callers still have to verify ownership, choose the strongest reliable identity and supply actual observation evidence. The key helper is a reusable producer foundation; the existing posture collector does not yet emit normalized graph records.

## Still pending in R4

Persisted immutable normalized observations and evidence, detailed per-layer coverage, timestamp/freshness selection, bounded snapshot readers and reference resolution from the shared contract; expanded bounded IAM collection; billing adapter and authorization; live AWS acceptance. Existing assessment HTTP representations and database revision 0025 remain unchanged. No migration or Supabase deployment is needed for this checkpoint.

## Verification scope

Focused cloud/API/worker regressions and static checks were run locally. Full-suite results are recorded in `IMPLEMENTATION_STATUS.md` after completion. The initial broad run encountered permission errors in the system pytest temporary directory; rerun uses a new workspace-owned temporary directory. No live AWS integration success is claimed.

The previous Linux, Compose, hosted Supabase and image acceptance results belong to the older 0025 source checkpoint. They have not been rerun against these source changes. The existing backend ZIP likewise remains the earlier checkpoint and has not been regenerated.
