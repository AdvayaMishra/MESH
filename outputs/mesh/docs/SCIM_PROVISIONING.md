# Reviewed SCIM provisioning

This feature creates a new external SCIM account **inactive**. It is separate from local MESH onboarding and from rehire. No live provider creation is claimed by the synthetic tests.

## Operator configuration

SCIM is bound to one fixed HTTPS authority per organization. Both flags default to false:

```json
{"ORG_UUID":{"base_url":"https://identity.example.com/scim/v2","token":"OPERATOR_SECRET","allow_provisioning":false,"allow_activation":false}}
```

Set `SCIM_BINDINGS` through protected runtime configuration. Enable provisioning only for a provider that supports the standard core User schema, `externalId` filtering with complete `totalResults`/`Resources`, creation with `active: false`, and subsequent identity/state reads. Activation additionally requires `allow_activation: true` and verified `active` PATCH behavior. Unsupported or ambiguous responses fail closed.

The adapter sends only username/email, a stable tenant/employee subject and the requested inactive state. It does not send payroll, identity images or employee investigation history. Redirects and compressed responses are rejected; JSON is limited to 128 KiB. The client checks a 20-second budget around headers/chunks and uses 10-second I/O timeouts. A blocking read can extend a budget check until that I/O timeout.

## Workflow

1. HR proposes `POST /api/v1/hr/lifecycle` with `employee_id`, `kind: "onboarding"`, and `provision_scim: true`. The organization must have an enabled binding and no SCIM account already linked to the employee.
2. An independent owner approves the plan. HR executes it. Human identity approval is required. Local onboarding is applied and external provisioning is queued; the plan remains `reconciliation_required`.
3. The existing organization-scoped outbox worker processes provisioning before ordinary event dispatch. Its generic consumer explicitly excludes provisioning messages, so a receipt cannot falsely imply that an account was created.
4. Successful discovery/creation verifies the exact subject, email, external resource ID and inactive boolean state. The account is linked and the plan reports `verified_inactive`.
5. An owner separately approves activation or records manual external reconciliation. External activation is never inferred from local onboarding.

Example HR request:

```json
{"employee_id":"EMPLOYEE_UUID","kind":"onboarding","provision_scim":true}
```

The existing worker command is sufficient:

```sh
python -m app.worker --organization ORG_UUID
```

## Crash and retry behavior

The worker commits a lease and then a permanent `creation_sent` reservation **before** issuing POST. One automatic POST is permitted for the stable tenant/employee subject while its intent history is retained. Discovery runs first. SCIM `externalId` does not itself provide server-enforced uniqueness, so a timeout must not trigger a blind second create request.

A lost response is recovered by exact-subject discovery. A crash after reservation but before sending can leave an account absent; automatic retries still do not repeat creation. After at most five attempts, the operation requires manual review. Leases last 180 seconds, and a stale lease cannot commit another worker's result. Creation reservations survive dead-letter retries and cancelled plans. Do not erase them or restart workers against a restored older database snapshot without reconciling external accounts first.

Account/authority changes, suspended organizations, revoked HR/owner authority, revoked employee access and changed identity approval stop provider work. Account creation is inactive by design; a remotely created but unlinked account may require manual cleanup if authorization changes or a process fails after the provider operation.

## Owner actions

All routes below are under `/api/v1/hr/lifecycle/{plan_id}` and require current owner authorization. References are audit ticket identifiers, not secret values.

| Route | Request | Result |
|---|---|---|
| `POST /provision-reconcile` | `{"reference":"verified-provider-ticket"}` | Performs exact-subject discovery and identity verification; links the verified existing account without another create request |
| `POST /activate-provisioned-scim` | `{"reference":"activation-ticket","external_activation_approved":true}` | Requires enabled activation, verifies identity, applies/observes activation, and verifies the resulting active state |
| `POST /cancel-provisioning` | `{"reference":"external-cleanup-ticket","external_access_revoked":true}` | Cancels unfinished external provisioning and fences pending work; records human attestation of external revocation |

Successful machine-verified activation is retry-safe and retained as `verified_active`. Other external integrations may still require manual reconciliation. Generic manual completion cannot bypass initial account verification. Human-attested completion is distinct from machine verification.

Cancelling provisioning does **not** undo local onboarding or deactivate a local employee. Use a separately approved offboarding plan for local revocation. A previously dispatched request can finish remotely even after cancellation; it requested an inactive account, and the operator must reconcile possible orphan accounts. No automatic external deletion is performed.

## Evidence and limits

Protocol and worker tests use synthetic HTTP/provider behavior. Real PostgreSQL tests verify the durable marker from an independent committed session before simulated HTTP, and recover a simulated lost response with one create attempt. Hosted rollback-only tests verify intent, JSON queries and cancellation without calling their synthetic SCIM authority. These checks do not establish live-provider compatibility or external legal/privacy approval.

Protocol references: [SCIM core schema](https://www.rfc-editor.org/rfc/rfc7643.html), [SCIM protocol](https://www.rfc-editor.org/rfc/rfc7644.html).
