# Authenticated organization discovery

GET /api/v1/users/me/organizations requires a genuine authenticated account/session, but no X-Organization-ID header. Request identity comes from the verified bearer identity, never an email, user ID, role or organization supplied by the browser. This is limited metadata discovery before tenant selection or MFA step-up; normal tenant authorization and privileged-MFA enforcement still apply to business operations.

The response is {items:[{organization_id,name,role,verification_status}],next_cursor:null|string}. Only the caller's active memberships in active organizations are returned. It contains no other members, email addresses, employee/private HR details or activity. Unknown users receive an empty page. Each returned organization metadata read is audited. The transaction resets its tenant context afterward.

Query parameters: limit1–100 (default20), cursor=canonical organization UUID. Ordering is organization UUID ascending. Use next_cursor until null; a page can be empty with a non-null cursor when its candidate memberships point to suspended/missing organizations. Responses do not grant membership or select a tenant automatically. Revocations/role changes are rechecked by existing business endpoints.

## Migration0029

A new membership lookup index is added. A separate SELECT-only RLS policy permits active membership rows for mesh.user_id only when mesh.organization_id is empty. The original tenant_boundary policies, table grants and all57 forced-RLS tables are preserved. The discovery policy grants no INSERT/UPDATE/DELETE capability and exposes no other business table. Nonempty tenant context continues to use the original tenant boundary.

The existing hosted project was upgraded0028→0029 with the version row locked, bounded lock/statement timeouts, an atomic transaction and verification that every pre-existing policy was unchanged. No business records or runtime grants were changed. The additive Supabase CLI SQL artifact is supplied; no historical SQL artifact was rewritten. CLI history was not updated because a compatible existing history catalog was unavailable; the actual application revision is recorded in alembic_version. Do not blindly replay all frozen SQL against this existing database; adopting CLI history later requires explicit reconciliation.

Verification:10new endpoint regressions plus the frozen SQL ordering gate; full default suite1313passed/34skipped. Separate native PostgreSQL16 run32/32integration cases passes, including predicate-free self discovery, denied cross-tenant writes, hidden private tables, dump/restore and fresh frozen SQL/policy equivalence. The two non-PostgreSQL integration cases still require dedicated Docker scanner and disposable Supabase Storage fixtures. Live restricted-role service checks pass for all4actual MESH accounts and an unknown-user negative; diagnostic audit writes were rolled back. These do not substitute for fresh interactive browser authentication acceptance.

The backend API and rebuilt bridge contract support discovery. The frontend welcome/organization-selection controls have not yet been changed to consume it, so the current UI can still ask for a UUID. This checkpoint implements backend support without rewriting frontend flows.
