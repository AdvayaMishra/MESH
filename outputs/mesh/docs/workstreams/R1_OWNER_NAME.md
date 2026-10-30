# R1-01 owner-name registration and profile contract

Implemented 27 October 2026 without a schema migration. Existing callers remain compatible.

`POST /api/v1/auth/register` accepts optional `owner_name`:1–200 printable Unicode characters, trimmed; blank/control-containing/oversized/non-string values fail validation. The temporary connected frontend captures this field. Login does not accept registration-only metadata fields.

The backend forwards only `{data: {owner_name: ...}}` alongside existing signup email/password/CAPTCHA fields to Supabase Auth. Supabase is still the sole password authority. No application password hash, duplicate identity table, new auth trigger or migration is introduced. Missing owner names omit the metadata field entirely; existing accounts are not backfilled with an invented name. Company name remains separate in organization creation.

Identity validation reads the current confirmed provider profile, not a potentially stale JWT metadata name. Invalid/legacy name metadata yields null without granting access or breaking an otherwise valid identity. `GET /api/v1/users/me` now has a typed `UserProfileOutput` contract and adds `name` and `owner_name` to existing identity/organization/role/email/employee fields. `name` prefers the scoped employee record, falling back to validated provider display metadata. `owner_name` is returned only for an owner membership.

User metadata is display data, not authority. Organization, role, active status, access cutoff, session revocation and privileged MFA decisions remain based on the existing verified identity and current database membership. No metadata role or client-selected demo role grants permissions. Profile reads remain self-scoped and tenant-validated. No generic profile-edit endpoint is claimed by this change.

Verification:26 new cases cover Unicode/normalization, malformed values, exact provider payload, legacy omission, forbidden login/role fields, malformed stored metadata, current-provider versus JWT precedence, employee-display precedence and role denial. The focused identity/JWT group passes47 cases; full Windows suite passes1,066/32 skips; static checks/mypy95 pass. Approved real preview accounts also verify Supabase-stored owner metadata through current provider-profile reads and the backend profile response. Those accounts were pre-confirmed by explicit fixture setup; this does not prove normal signup email delivery, CAPTCHA, OTP expiry/resend or production settings. Those remain R1-02/R1-03.

Provider references: [Supabase signup metadata](https://supabase.com/docs/reference/javascript/auth-signup), [Supabase user data storage and authorization cautions](https://supabase.com/docs/guides/auth/managing-user-data). The deployed application schema remains0028/57 forced-RLS tables and all26 frozen SQL artifacts remain unchanged.
