# R1 / R4 live acceptance configuration boundary

Latest SMTP update,29October: authenticated Gmail SMTP is now configured and functionally verified in Supabase and MESH. Confirmation/recovery templates and subjects are deployed; actual controlled-inbox signup/resend/recovery/invitation evidence and fixture cleanup are recorded in `gmail-live-acceptance-results.json`. Temporary Auth mail quota3 was restored to2. This supersedes missing-SMTP/template observations below. CAPTCHA and production HTTPS site are not configured, and SCIM/OCR operational requirements remain open. Secrets stay private and no production release is claimed.

Latest 29 October update supersedes the missing-token observation below: project Auth management access is now configured and verified. Hosted password minimum12 and email OTP expiry600seconds were applied and independently read back. Custom SMTP/templates, CAPTCHA, production domain/redirect policy and remaining SCIM/OCR acceptance are still pending. See [current hosted Auth progress](R1_AUTH_ACCEPTANCE.md). Token values remain private; no real user password or identity was changed.

29 October update: protected-file presence checks again found no production SMTP credentials, mail encryption key, Supabase management token or SCIM bindings. The user explicitly confirmed that these prerequisites and authorized OCR evaluation material are not configured yet. The new read-only Auth management checker returns `management_authority_missing`, with no network mutation or delivery claim. Source Auth templates and the private-corpus OCR evaluation harness are ready for review/use once the required inputs are supplied; they are not deployed settings or production acceptance.

Checked 26 October 2026 against the current backend runtime and known protected setup file. This lists prerequisites; it does not claim an integration succeeded because a key exists. No credential values are included. Backend-only scope; no frontend or other workstream changes are authorized by this document.

## Observed configuration

| Prerequisite | Current observation | Work that cannot honestly be marked complete |
|---|---|---|
| MESH production invitation SMTP | Authenticated TLS SMTP not configured | Actual invitation/resend delivery and bounce/outage acceptance against the chosen mail provider |
| Supabase Auth administration | No management token in runtime/known setup file | SMTP/templates/CAPTCHA/refresh/MFA policy administration and provider configuration verification |
| Supabase public Auth flags | Email enabled; signup enabled; mailer autoconfirm disabled; unexposed flags unknown | Public flags do not prove inbox delivery, CAPTCHA enforcement or recovery acceptance |
| SCIM directory bindings | 0 configured, 0 provisioning-enabled, 0 activation-enabled | Real dedicated-account creation, deactivation and restoration acceptance |
| AWS posture roles | 0 organization bindings | Actual read-only inventory/IAM/resource-policy acceptance |
| AWS billing roles | 0 separate organization bindings | Actual Cost Explorer feed/account/period/currency/provenance comparison |
| Local runtime mode | Development; privileged MFA not required locally | This is not a production identity configuration; production validation rejects disabled privileged MFA |

## Configuration to supply through protected operator channels

- MESH SMTP: `SMTP_HOST`, `SMTP_PORT` (1–65535), `SMTP_FROM`, `SMTP_STARTTLS=true`, `SMTP_USERNAME`, `SMTP_PASSWORD`; retain the independently generated `MAIL_ENCRYPTION_KEY` for queued invitations. Set `INVITATION_BASE_URL` to the fixed HTTPS acceptance endpoint without credentials, query, fragment, backslashes or whitespace. Configure domain authentication with the selected provider. MESH SMTP and Supabase Auth SMTP are separate.
- Supabase: an authorized project administrator configures actual SMTP, confirmation/recovery templates and redirect/OTP/CAPTCHA/refresh/MFA policies. A management PAT, if used for operator automation, belongs in an operator secret store/`SUPABASE_ACCESS_TOKEN`, not the application runtime or frontend. Existing database/Storage credentials do not substitute for this authority.
- SCIM: per-organization `SCIM_BINDINGS` with a fixed trusted HTTPS directory root and backend token; explicit provisioning/activation permissions only when authorized. Use dedicated disposable test identities, never existing employees as destructive test fixtures. See `INTEGRATION_CONFIGURATION.md` and existing lifecycle integration docs for the approval/revocation/restoration protocol.
- AWS inventory: `AWS_ROLE_BINDINGS`, a trusted source workload identity/short-lived SDK credential chain, approved target role trust/read permissions and region. The role must additionally permit the bounded IAM authorization-detail/policy-version and S3 policy reads documented in `R4_IAM_BILLING_FOLLOWUP.md`.
- AWS billing: separate `AWS_BILLING_ROLE_BINDINGS`, target trust and Cost Explorer activation/access with `ce:GetCostAndUsage`. Account scope is fixed by the verified role account; no tenant-supplied account override. Start the opt-in billing worker for the actual organization. See `R4_BILLING_COLLECTIONS.md` for request replay, fees/uncertainty and comparison checks.

Do not paste credentials into chat, commit them, include them in examples, use production employees/real identity documents as test fixtures, or fabricate account identifiers. Existing protected runtime configuration is `outputs/mesh/.env`; the separate operator setup file is `work/supabase-setup.env`. Their values remain private.

Both AWS adapters now send the canonical MESH organization UUID as STS `ExternalId`. The role template in `infrastructure/aws/mesh-readonly-roles.json` requires that exact value as well as the exact source workload role. Existing custom role trusts that require another external ID need an authorized migration; collection APIs offer no arbitrary override or fallback without it. Live acceptance must verify correct-ID success and omitted/wrong-ID denial before accepting a customer role. Local SDK tests prove request binding and failure behavior, not the actual provider trust policy.

## What has already been completed locally

R4 now has verified-session collection adapters, immutable asset/IAM context and readers, bounded IAM/group/policy/boundary/trust and S3 resource-policy observations, plus durable finance-authorized billing admission/storage/worker/report APIs under Supabase0027. Failure, replay, cancellation/revocation, ambiguity, tenant isolation, exact signed amounts and synthetic isolation are tested. Real provider acceptance remains distinct.

R1 already has Auth/MFA/session, mail/outbox and HR/SCIM lifecycle adapters and local tests; earlier temporary Auth/MFA/Storage/OCR fixture evidence is separately retained. The missing live prerequisites above are not repaired by repeating those fixtures. No new outbound email, SCIM identity mutation, AWS query or provider policy change was performed during this prerequisite review.

Subsequent R1 local completion at revision 0028 adds audited document preservation/independent release, held-record database guards, bounded expiry, tenant/object-reference validation, OCR publication fencing and a metadata-only HR review queue. See [preservation and review API contract](R1_DOCUMENT_PRESERVATION.md). This does not remove the production privacy/OCR or real-provider acceptance requirements above.

## Conditional SCIM updates

Each `SCIM_BINDINGS` entry defaults to `require_version=true`. Before changing `active`, the adapter verifies the target identity and reads its version from HTTP `ETag` or `meta.version`. If both exist they must agree. Only one bounded strong/weak quoted ASCII entity tag is accepted; wildcard, multiple tags, malformed and injected headers fail before mutation. PATCH sends this exact value as `If-Match`, and a successful response is followed by an identity/state read.

HTTP 412 becomes a sanitized conflict (409), with no unconditional fallback. Missing versions fail closed (503) when a change is needed. An already-correct identity needs no mutation. A provider that cannot implement versioning requires an explicit operator `require_version=false` binding; this weakens concurrency protection. Even that mode uses any supplied version and never bypasses a failed precondition. Existing bindings therefore need a version-capable provider before their next state change, or an explicit acceptance of the weaker mode.

Local protocol tests and a real loopback TLS SCIM fixture verify conditional deactivation, a concurrent-change refusal without mutation and rejection of an untrusted certificate. These use synthetic identities and an ephemeral test CA, not a real directory. Real-provider creation, revocation/restoration and race/error acceptance remain pending the configured dedicated test directory. Versioning semantics follow [SCIM RFC 7644 section 3.14](https://www.rfc-editor.org/rfc/rfc7644#section-3.14).
