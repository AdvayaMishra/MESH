# Finding identities and observation history

Migration 0023 adds immutable, tenant/repository-scoped identities. Every new completed scan retains its own findings and exact job/commit provenance. Matching observations link to one identity; each observation keeps its own severity, disposition and audit history.

The `exact-observation-v1` policy hashes the organization, repository, scanner, rule ID, file path, line, optional column and optional dependency name/ecosystem/version using canonical JSON and SHA-256. Severity is excluded. Changed locations or package versions create distinct identities. This is exact recorded metadata matching: it does not establish semantic equivalence, an exploitable vulnerability, or a verified fix. An advisory ID shared by different packages is not enough to merge them.

New observations start open. A resolved or accepted-risk observation does not silently decide the disposition of a later scan. Missing observations do not imply remediation. Legacy records retain unknown scan/commit provenance even after indexing.

| API | Contract |
|---|---|
| `GET /api/v1/repositories/{repository_id}/finding-identities` | Authorized paginated groups, total group count, unindexed observations, scanner/latest-status filters, first/last observation, status counts, distinct known scans and unknown provenance count |
| `POST /api/v1/repositories/{repository_id}/finding-identities/index` | Fresh scan authority; body `{"limit":200}`, range 1–500; links only previously unindexed records and reports remaining count; repeat-safe |
| `GET /api/v1/finding-identities/{identity_id}/observations` | Authorized paginated raw observation history, ordered by creation time and ID |

Latest means observation creation time, with ID as a deterministic tie-breaker. It does not mean repository branch head or newest code in the deployment. Status filtering applies to the latest observation; counts retain the full linked history. Unindexed counts use the corresponding raw observation filter and are reported separately.

Database protection includes forced RLS, an exact organization/repository identity foreign key, uniqueness of scoped fingerprints, an update/delete denial trigger and runtime SELECT/INSERT grants only. Browser API roles cannot access these tables directly. Indexing is audited and bounded; no automatic historical bulk rewrite occurs during deployment.

Evidence: seven focused regression cases; real PostgreSQL immutable/scoping/history case; rollback-only hosted indexing and grant checks. These checks use synthetic records and do not alter real finding decisions.
