# Local development

Use Python 3.12+ and Docker Compose v2. No frontend dependencies are needed. From the repository root:

```sh
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install -r requirements-dev.lock -e .
pytest -q
ruff check .
mypy backend/app
```

Copy `.env.example` to `.env`, generate independent random URL-safe passwords (24+ characters), then configure Supabase as described in SUPABASE_SETUP.md. Compose exposes only the API and local mail UI on loopback. PostgreSQL and Redis stay on the Compose network.

```sh
docker compose up --build
docker compose logs api
```

The migrate service runs with administrator credentials and creates a restricted runtime role. The API and worker use the runtime role. Readiness refuses database owner/superuser/BYPASSRLS credentials. Liveness only confirms that the process is alive. Readiness also requires migrated tables, Redis and a configured identity URL; it does not actively probe Supabase.

Use `/docs` to exercise implemented routes with Supabase tokens and X-Organization-ID. Create an organization with a verified provider identity. Invitations sent through local Mailpit can be inspected at `http://localhost:8025`; the frontend link is a contract only because no frontend is supplied. Accept through the API using token and organization ID.

After creating an organization, set WORKER_ORGANIZATION_ID to its UUID and configure MAIL_ENCRYPTION_KEY, then run `docker compose --profile worker up worker`. The worker delivers encrypted invitation mail and records receipts for other topics. Scanner execution uses a separate trusted Docker host launcher described in docs/SCANNING.md. Optional documents profile supplies ClamAV and retention; configure private Supabase Storage separately.

Without Docker or Supabase credentials, run SQLite-backed automated tests. Provider calls use explicit test doubles. There is no deployable fake identity provider or auth bypass. Reproducible offline owner registration with a local identity server remains pending; basic domain/service tests need no paid service.

The plain runtime/development locks preserve tested version snapshots. Docker runtime and isolated package-building now use separate hash-enforced wheel locks; see [artifact integrity](docs/ARTIFACT_INTEGRITY.md). The development-tool snapshot remains outside that hash guarantee. Linux image and Compose compatibility have passing checkpoint evidence in IMPLEMENTATION_STATUS.md. `scripts/seed_demo.py --owner-id <existing-auth-uuid> --owner-email <verified-email>` creates a new explicitly synthetic development organization and VADER scenario. It creates no Auth account and grants no identity bypass.

Never run `docker compose down -v` on data you need; it deletes the database volume. Apply migration updates with reviewed backups. Production secret management, TLS, persistent Redis policy and production email transport require separate configuration.
