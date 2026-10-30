# Testing and validation limits

Run `pytest -q`, `ruff check .`, `ruff format --check .` and `mypy backend/app` after installing `.[dev]`. Export OpenAPI with `python scripts/export_openapi.py`. CI additionally configures Bandit, pip-audit, Gitleaks and container build; local execution and remote CI are distinct evidence.

SQLite fixtures enable foreign keys and override identity explicitly. They exercise authorization, composite tenant relationships, invitations, deterministic payroll, domain proof state, scanner metadata sanitization, webhook HMAC, body bounds, project transitions, VADER deduplication/correlation, simulated response separation and outbox receipt idempotency. Provider adapters use httpx MockTransport.

These tests do not demonstrate PostgreSQL RLS, real identity/CAPTCHA/OTP policy, distributed Redis behavior, SMTP delivery, worker concurrency, real repository sandboxing or cloud APIs. Never infer those results from SQLite tests.

The opt-in PostgreSQL suite is now `backend/tests/test_postgres_integration.py`. Configure MESH_POSTGRES_ADMIN_URL only for a disposable database named mesh_test_*. It provisions a random restricted test role and exercises unscoped RLS reads, cross-tenant writes, role checks, audit triggers, transaction-context reset and concurrent audit append serialization. It is skipped without a configured server. Docker and private Storage opt-in suites are described in docs/INTEGRATION_CONFIGURATION.md. The full backend journey uses explicit identity, email, malware and Storage test doubles, so it is not a live Supabase end-to-end result.

See IMPLEMENTATION_STATUS.md for actual commands and observed results. Performance and production security testing have not been completed.

On Windows, if an old pytest temporary directory has restrictive permissions, run with a new workspace directory rather than changing global permissions:

```powershell
$meshTestTemp = Join-Path $PWD (".test-work-" + [guid]::NewGuid().ToString("N"))
python -m pytest backend/tests -q -p no:cacheprovider --basetemp=$meshTestTemp
```

The 0018 finance checks include concurrent real PostgreSQL cost receipt retries, tenant-bound actor foreign keys, canonical money, budget replay/variance, paired usage quantities/units and explicitly synthetic future billing adapters. See docs/FINANCE.md and docs/MASTER_ACCEPTANCE.md. A fixture setup error is a failed run until a clean rerun succeeds; it must not be counted as an application pass.
