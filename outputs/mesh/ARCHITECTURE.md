# Architecture decisions

- ADR 001: Modular monolith with independent outbox worker. PostgreSQL is the production database. SQLite is restricted to isolated automated tests, never a production replacement for RLS.
- ADR 002: Supabase Auth owns passwords, OTP, refresh and MFA. The application verifies asymmetric JWTs against configured JWKS with issuer/audience constraints and consults active membership on every request. No second password database, locally issued JWTs or default development identity.
- ADR 003: Organization is selected by X-Organization-ID but authorized against the authenticated subject and active membership. Database RLS is a second boundary. Application runtime must use a non-owner, non-BYPASSRLS PostgreSQL role. Worker jobs must set their own tenant context.
- ADR 004: Typed domain models and service functions. No generic arbitrary-table CRUD. Employee documents and complaints are excluded from owner permissions.
- ADR 005: Durable transactional outbox rather than Kafka. Database business changes, audit metadata and outbox messages commit together. Consumers must be idempotent; external delivery is at least once.
- ADR 006: Security decisions and financial calculations are deterministic. Detection is evidence for investigation, never proof of misconduct. Responses simulate effects only, after analyst approval.
- ADR 007: Live scanner execution, cloud mutation and external AI are disabled until their credentials and operational boundaries are validated. A temporary directory is not a sandbox.
- ADR 008: No frontend source or frontend integration. FastAPI OpenAPI is the future frontend contract.
- ADR 009: Docker access belongs only to a dedicated trusted launcher. API containers receive no Docker socket. Checkouts use bounded tmpfs volumes; separate analysis containers have no network. Source configuration and adapter tests do not establish validated containment.
- ADR 010: Incremental frozen schema migrations preserve 0001. Payroll policies are immutable versioned component formulas with retained calculation snapshots. Audit chains serialize per tenant using PostgreSQL NO KEY UPDATE locks to remain compatible with child-row foreign-key locks; external chain anchors remain pending.
- ADR 011: Private ID images are gated by image validation and ClamAV and reviewed by humans. Model context contains numeric aggregates only. External gateways and cloud sessions require explicit operator configuration and tenant bindings.

API → JWT verifier → active membership + permission → tenant transaction → domain service → tenant models + audit + outbox. A separate worker leases outbox rows with PostgreSQL SKIP LOCKED. Telemetry flows through rule evaluation, actor/time correlation and risk explanation before simulated response approval.
