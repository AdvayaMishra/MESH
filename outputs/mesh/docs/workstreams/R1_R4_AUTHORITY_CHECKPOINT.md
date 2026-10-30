# R1/R4 authority hardening after 0028

Backend only. No schema revision, endpoint, frontend or R3 consumer change is required. Supabase remains at deployed 0028 with 57 forced-RLS application tables. Existing hold/queue APIs and cloud-context contract 1.0.0 remain compatible.

## R1 fresh document access

All HR document operations now use one shared document authority boundary: holds/history/release/queue, signed links, OCR reads, human decisions, OCR retry/manual review and API-triggered expiry. It checks current organization status, active HR membership, configured privileged MFA, membership access cutoff, tracked-session revocation/expiry and presented-token expiry. Production requires a tracked session; only existing isolated test mode permits fixtures without one.

The tenant lock is acquired before these checks, and organization status is explicitly refreshed afterward. A previously cached active organization cannot authorize a request that waited behind a committed suspension. A real PostgreSQL test retains the old object in one session while another suspends the organization under its lock, then verifies the waiting request is denied.

Uploads repeat current authorization after malware/image validation and before creating the document reference or contacting private Storage. They lock/refresh the employee's user/status, require self ownership and onboarding/active employment, and recheck organization, membership, session and access cutoff. Tests revoke access, suspend the organization, offboard/reassign the employee or set a cutoff during scanning; no revoked upload reaches Storage. Existing image/size/malware/key-binding gates still apply.

Maintenance retention remains an explicit selected-tenant system operation for suspended tenants; it still honors holds and does not gain document-reading privileges. Fresh checks are a request-boundary guarantee, not a claim that an already-issued provider signed URL can be synchronously revoked or that a remote operation can be recalled after dispatch.

## R4 tenant-bound STS context

Both posture and billing adapters now validate the MESH organization UUID before creating an STS client or resolving its SDK credential chain, then send its canonical value as `ExternalId` with their existing fixed session name, 900-second duration and restrictive session policy. Collection requests supply no external-ID override. Denial fails with the existing sanitized 503; there is no application retry without the ID. Existing billing paid-call replay/dispatch fencing is unchanged.

The AWS role template now requires `sts:ExternalId` equal to `MeshOrganizationId`, in addition to the exact trusted workload role. The source principal, target role permissions, session restrictions and account verification remain required. An external ID is tenant context and is not an AWS credential or secret. See [AWS external-ID guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_third-party.html) and [STS request parameters](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html).

An existing custom trust policy requiring a different external-ID value must be reviewed/migrated before using these adapters. A policy that accepts requests without any external-ID condition may still accept this call; successful assumption alone does not prove tenant enforcement. Real acceptance must establish correct-ID success plus omitted/wrong-ID denial before onboarding a customer binding. No such live role, policy update, deployment, AWS query or paid collection was performed without authorized AWS configuration.

## Evidence and limits

The current Windows suite passes 1,002 tests with 31 opt-in skips. All 29 native PostgreSQL cases, fresh frozen SQL and restore checks pass. Eight hosted rollback-only preservation checks pass against the strengthened authority code with no committed fixtures or Storage objects. Ruff/format, mypy across 93 application modules and Bandit pass. Current-image Linux/Compose and exact fingerprint evidence are recorded in `IMPLEMENTATION_STATUS.md` and `document-authority-checkpoint.json` when complete. OpenAPI remains 185 operations/159 paths.

Local SDK fixtures prove tenant request binding, invalid-tenant rejection before SDK access, sanitized failures and absence of an unconditional fallback. They do not establish provider trust enforcement, mail/SCIM/Auth journeys or production acceptance. Missing protected external configuration and the existing OS advisory gate remain unresolved; production clearance remains false.
