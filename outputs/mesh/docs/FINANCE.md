# Finance contracts and provenance

Current R4 handoff: [setup/status/sample API contracts](workstreams/R4_STATUS.md). The separate AWS billing adapter and durable admission/worker/report APIs are implemented under0027 and preserved through0028. Explicit development samples are now readable through a separate finance-authorized endpoint, always labelled synthetic and excluded from normal finance records/collection history. They never become an automatic fallback for failed live calls. Actual AWS account/feed acceptance remains unconfigured; historical fixture-only wording below describes the earlier finance checkpoint.

Cost submissions require a client-generated UUID `request_key`. Retrying the same key, actor and canonical body returns the original record; changing the body or actor returns HTTP 409. Authorization is checked again on every retry. Historical records retain unknown receipt provenance. Request keys are scoped to the organization and do not replace authorization.

Budgets have one value per organization, month and currency. Identical creation retries return the existing budget; a conflicting amount returns 409. The existing per-budget variance endpoint remains available. `GET /api/v1/finance/budget-variance` returns observed and budgeted periods, actual minus budget, percentage and over-budget state. A missing budget produces null variance; a zero budget produces null percentage.

`GET /api/v1/finance/usage` groups recorded cloud/infrastructure quantities by month, provider and unit. Currency, provider and month filters are available. Quantities in different units are never added together. These are reported records, not independently measured infrastructure or a provider invoice.

Summaries use bounded SQL aggregation and deterministic Decimal arithmetic. Forecasting requires three consecutive observed months. The existing what-if endpoint applies an explicit proportional change to historical totals. None of these calculations use AI.

`app.billing` defines a bounded provider adapter boundary and explicitly labeled synthetic fixtures for AWS, Azure and GCP. Live adapters fail closed until an authorized account binding and actual provider implementation exist. No real cloud billing connection or automatic import has been validated. Synthetic billing observations are confined to tests; they are not inserted into hosted production data.

Migration 0018 adds nullable receipt and usage fields, tenant-bound actor foreign keys, organization/request-key uniqueness, receipt completeness and quantity pairing constraints. Apply through the documented migration workflow after isolated database verification. The frozen Supabase SQL file is `20261025000600_finance_idempotency.sql`; do not replay the fresh-project bootstrap against the deployed project.
