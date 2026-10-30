# Reviewed employee rehire and external restoration

Rehire is an explicit lifecycle operation. It never reverses an old offboarding plan in place.

1. HR proposes `kind: "rehire"` with an explicit nonprivileged role and department. The employee must be offboarded, its membership inactive, its identity human-approved, and its prior offboarding reconciliation completed.
2. An independent active owner approves the new plan.
3. HR executes it. Local access stays revoked and the plan waits for owner activation review.
4. The owner reviews external access and performs provider-wide session revocation. The owner may request opt-in SCIM restoration or handle external systems manually.
5. The owner submits `rehire-activation` with a reference and explicit true acknowledgements. The backend rechecks current approval, organization, employee, membership and exact external-account inventory before activating local access.

| Endpoint suffix under `/api/v1/hr/lifecycle/{plan_id}` | Purpose |
|---|---|
| `/restore-scim` | Owner queues restoration of the exact reviewed SCIM account; requires operator `allow_activation: true` |
| `/rehire-activation` | Owner records session/external-access attestations and activates local membership |
| `/abort-rehire` | Owner attests external access is revoked and abandons an incomplete rehire while local access stays revoked |

Both restoration and activation accept `reference`, `provider_sessions_revoked: true`, and `external_access_reviewed: true`. Abort accepts `reference` and `external_access_revoked: true`. These are human attestations, not fabricated provider verification. They are retained in plan history/audit. Generic reconciliation and inverse-plan endpoints cannot bypass the explicit rehire workflow.

SCIM activation is disabled by default. `SCIM_BINDINGS` may include `allow_activation: true` only after the operator authorizes and validates that provider. The worker verifies external user ID, email and boolean activation state before and after PATCH; it rechecks the exact reviewed authority/account binding, requesting owner, original approver, tenant and revocation state. Retries are bounded and surface dead-letter/manual-review states. Verified external restoration does not automatically activate MESH access. Offboarding revocation may continue for suspended tenants; restoration cannot.

Activation removes retained project assignments through `mesh_rehire_clear_project_grants(text)`, a narrowly granted function. Runtime direct DELETE remains prohibited. Old proposer-based project access and old senior review eligibility also cease across the access boundary. New project assignments require a fresh authorized action. Queued/running pre-rehire scan and cloud jobs are cancelled. Employment/payroll history is retained; new compensation terms remain a separate HR review.

The membership `access_not_before` boundary rejects JWTs whose issued-at timestamp predates or equals activation. Timestamp comparisons preserve actual instants across database timezone offsets. The boundary alone does not revoke provider refresh tokens: the owner must separately perform provider-wide session revocation and truthfully record it. A fresh sign-in after activation is required. No provider-wide revocation is claimed from a local timestamp alone.

Exact-account review digests bind tenant, user, provider, external ID, normalized email and configured authority. Changing accounts, email, authority or account inventory after review requires fresh review. Rotating only a credential does not change the reviewed authority. Legacy plans without binding digests cannot automatically mutate external accounts; offboarding manual reconciliation remains available.

Evidence uses synthetic identities and mocked SCIM HTTP unless a report explicitly states otherwise. Real SCIM account creation, a live organization's restoration journey, and provider-wide session revocation have not been validated. Reviewed inactive provisioning is implemented separately in SCIM_PROVISIONING.md. Live provider acceptance remains unverified; no production readiness is claimed.
