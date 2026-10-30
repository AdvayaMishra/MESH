# Reviewed lifecycle compensation

`POST /api/v1/hr/lifecycle/{plan_id}/compensation`, HR only, takes a bounded reason (8–1000 characters). It creates an inverse proposed plan for a completed onboarding, role change, promotion or department transfer. It does not change access when requested. Repeating the request returns the same recorded inverse plan.

Current access must still match the original executed outcome. Unrelated later access changes cause 409 and require an explicitly reviewed replacement. Role/department inverses capture current access and propose the original snapshot. An onboarding inverse proposes offboarding; it follows the existing revocation and external-reconciliation workflow.

The inverse requires a fresh independent owner decision and HR execution. Execution rechecks the approving membership is still an active owner, rejects self approval and verifies the current access snapshot. Source and inverse histories retain their link and reason. Original completed history remains present.

An offboarding inverse is rejected. This API never restores revoked access. Rehire/reactivation remains a separate reviewed workflow to implement; it is not silently treated as an ordinary compensation. Existing queued SCIM revocations, partial failures, verified readback and manual-attestation fallback remain in effect. External provisioning/restoration and atomic rollback across providers are not claimed.

Tests cover fresh approval, repeat requests, stale snapshots, owner deactivation/role change, tenant/role denial and preservation of revoked membership. The hosted workflow verifier exercises a fictional transfer/inverse under a transaction that is entirely rolled back.
