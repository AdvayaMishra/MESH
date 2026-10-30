# Backend handoff — 30 October 2026

Current hosted application revision: 0029; 57 forced-RLS tables. Frozen earlier migration files were preserved. Only the timestamped membership-discovery SQL and Alembic 0029 were appended. Do not overwrite or renumber the applied migration when merging friend-owned work; reconcile the Alembic graph and any Supabase CLI history explicitly.

Current API: 192 operations / 165 paths. New organization self-discovery and invitation list/delivery APIs are documented; the frontend selection/invitation-list controls have not yet consumed them. Owner AI currency resolution is corrected while remaining a labelled local template provider. No R2/R3 code or R3/R4 shared asset/IAM contract was modified.

R1 security now includes fresh invitation creator/resender/acceptance authority, SMTP skip outcomes, active-organization refresh and UTC-instant expiry. No new paid/provider configuration, genuine identity verification claim or production deployment was fabricated. Source integration is in the canonical workspace. The earlier portable ZIP was not regenerated.

Verification: 1,323 default tests pass; 36 default skips include 34 PostgreSQL cases that passed separately under native PostgreSQL. The other two need dedicated Docker scanner/disposable Storage fixtures. Final focused invitation tests: 28 passes. Static checks pass. Native dump/restore and fresh frozen SQL/storage-policy equivalence pass. Scoped live membership and permission checks pass with rolled-back diagnostics; actual browser/provider journeys retain their own historical evidence and outstanding limits.

External/manual acceptance still requires a production HTTPS host/hostname and service policies; a real authorized SCIM directory; representative authorized OCR material and privacy/retention decisions; reviewed OCR image/advisory clearance and deployed screening; and the explicitly deferred AWS bindings/account checks. Do not turn these green using synthetic fixtures.
