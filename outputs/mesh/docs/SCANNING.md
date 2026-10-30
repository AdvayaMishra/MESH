# Authorized repository scanning

The API queues immutable-commit jobs; it never receives repository paths or executes source. Owner binds a repository to a project after the GitHub App confirms access. Operators must bind each GitHub installation to its authorized MESH organization in GITHUB_INSTALLATIONS. Supplying an installation ID alone cannot grant access to another tenant's installation. Configure a contents-read-only GitHub App, GITHUB_APP_ID and a protected GITHUB_PRIVATE_KEY environment secret. Tokens are short-lived and never stored in the database.

On a dedicated Linux Docker host:

```sh
docker build -f security-engine/Dockerfile -t mesh-scanner:local .
docker build -f security-engine/Fetch.Dockerfile -t mesh-fetch:local .
python -m app.scan_worker --organization <authorized-uuid> --loop
```

The trusted launcher uses the Docker CLI. Do not mount its socket in the API container. Treat launcher access as host-level privilege and use a dedicated host/VM. Apply network egress allowlists permitting only GitHub for the fetch container; static analysis containers use `--network=none`.

Checkout lives in a 384 MiB tmpfs Docker volume with noexec/nosuid/nodev. Fetch validates repository syntax and a full 40-character commit SHA, disables hooks/submodules/external Git protocols/redirects, enforces timeouts and rejects excessive file counts/sizes. Credentials pass through stdin into container tmpfs. Each scanner runs under UID 10001 with read-only source and filesystem, dropped capabilities, no new privileges, bounded tmpfs, memory/CPU/PID limits and bounded output. Cleanup removes fetch/scan containers and volumes on normal/error exits. Host crashes still require an operational janitor for `mesh.temporary=true` volumes.

Semgrep uses bundled local rules, disabled metrics and no rule downloads. Bandit performs AST analysis only. Gitleaks uses trusted configuration and complete redaction; adapters persist bounded rule/location/severity fields and discard code/evidence/secret values. The bundled Semgrep rules are a small baseline, not comprehensive language coverage. OSV extracts exact PyPI requirements pins and npm package-lock entries without package installation or repository build scripts. It queries only package metadata, handles pagination and leaves severity as `info` when batch responses omit severity.

Repository suppressions are not trusted: Bandit ignores nosec directives, Gitleaks uses a trusted empty ignore file and ignores inline allow comments, and Semgrep scans a private tmpfs copy with empty ignore files and disabled inline suppressions. That private copy shares the 128 MiB container temporary-space cap, so larger inputs can fail closed and require a reviewed resource-policy change. Tool parse errors fail the scan rather than being normalized to zero findings. The separate actual Docker integration test passed these trusted-fixture suppression and containment checks on the current core-only image.

Scans use row claims, expiry leases, stale-worker fencing, permission rechecks, retries and dead-letter states. A failed scanner is not reported as a clean scan. Request idempotency binds tenant+request_key to repository+commit. Poll `/scans/{id}` for progress; SSE is not implemented.

An approved disposable Alpine/QEMU VM provides an actual Docker 29.9.2 engine. The current core-only scanner image passed all three tools, dependency extraction and containment. The exact fetch Dockerfile image built successfully; actual authorized GitHub checkout/webhooks remain unvalidated. Six public image inputs are digest-pinned and runtime dependencies are hash-frozen. See docker-scanner-results.json and PHASE_1_3_STATUS.md for evidence and remaining acceptance.

Contracts checked against primary sources: [OSV batch API](https://google.github.io/osv.dev/post-v1-querybatch/), [Semgrep metrics control](https://github.com/semgrep/semgrep/blob/develop/metrics.md), [Gitleaks image source](https://github.com/gitleaks/gitleaks/blob/master/Dockerfile).

## Scanner resource recovery

New fetch/source/scan resources carry managed-by, temporary, kind and creation-epoch labels. On the dedicated Docker host, run python -m app.scan_janitor for a dry run; add --apply for deletion. It accepts only correctly named MESH-owned resources older than two hours, inspects labels again before deletion, processes containers before volumes, never runs Docker prune and reports per-resource failures. Pre-label legacy resources require operator review. Fixture tests cover ownership, age, dry run and cleanup failure; live janitor crash-recovery validation remains separate from normal scanner cleanup.

Current static manifest and live/native test coverage is recorded in PHASE_1_3_STATUS.md and scanner-live-results.json. Requirements lockfiles and npm lockfile versions 1–3 are supported. Unsupported/unpinned requirement lines and unsafe references fail rather than producing a clean result. Exact-version marker branches are conservatively included without evaluating them. Semgrep source files over 1,000,000 bytes fail the scan; unsupported manifest/language families remain outside coverage.


## Latest runtime acceptance (24 October 2026)

Actual Uvicorn and temporary native Redis passed nine HTTP/runtime checks: readiness 200, real login/MFA/logout, persisted self-session isolation, tenant denial, body limits and account throttling, followed by Redis-outage readiness/business 503. Three separate worker-process checks passed for committed Mailpit delivery, receipt replay without duplication and fixture cleanup. Five ClamAV checks passed using current officially signed definitions, including clean PNG and standard EICAR detection through the upload gate. All temporary services were stopped after testing. The actual Docker engine and all-three-tool containment tests have passed; Compose acceptance is recorded separately. Native Semgrep passed the three bundled rules using the official core with documented legacy workers under approved execution. See PHASE_1_3_STATUS.md for exact remaining access requirements and reproducible commands.


Latest continuation: all three native scanner tools passed trusted synthetic fixtures; registry lockfile coverage now includes Pipenv/Poetry/uv. The combined real-provider document journey passed 19 checks with rollback-only database fixtures and verified external-object cleanup. Six container source images are frozen by verified manifest digest. See docs/PHASE_1_3_STATUS.md and the corresponding JSON evidence for limits.


## Manifest coverage and image inputs

Static inventories include requirements pins, npm lockfiles v1–v3, Pipenv lockfiles including custom categories, Poetry lockfile schemas 2.0/2.1, uv v1 registry packages, and bounded CycloneDX JSON 1.5/1.6 subsets named bom.json or *.cdx.json. CycloneDX components need exact versioned PyPI/npm purls matching their component versions. Nested components are bounded; qualifiers and repository URLs are not emitted to OSV. Unsupported schemas, package sources, components and excessive inventories fail closed. This is not full CycloneDX schema validation or support for every ecosystem. No package manager, build hook, repository import or external reference is executed. uv's format can evolve; newer unsupported versions are rejected explicitly.

Public container inputs are now pinned by verified manifest digest; see container-image-lock.json. Image build/runtime validation remains separate, while the seven runtime Python packages and native artifact are separately hash-frozen. Repository analytics uses tenant/repository-scoped SQL grouping instead of materializing every finding across scan history.

Format references: [uv lockfile layout](https://docs.astral.sh/uv/concepts/projects/layout/), [Pipenv lockfile](https://pipenv.pypa.io/en/stable/pipfile.html), [CycloneDX JSON reference](https://cyclonedx.org/docs/1.6/json/), [package URL specification](https://www.packageurl.org/docs/purl/introduction).


## Current containment and inventory contract

The host must be Linux amd64 with enforced memory/swap, PID and CPU limits and default built-in seccomp. Official Semgrep also requires a compatible modern x86 CPU. Containers disable swap and explicitly clear Docker client proxy defaults to prevent accidental credential injection. Six public image inputs use exact manifest digests; security-engine/requirements.lock freezes seven runtime Python packages with SHA256 hashes, and semgrep-artifact.lock separately freezes the native-engine wheel. The exact delivered scanner Dockerfile builds with online hash-enforced downloads, and that image passes Linux pip check, exact versions, absent unused frontend packages and the actual containment/all-tool test.

A bounded, isolated read-only keeper container holds the no-exec RAM volume mounted across fetch and sequential scanner containers. Without it, local tmpfs volumes are erased on their last unmount. The launcher rechecks the keeper and fails rather than accepting an empty scan after its loss. Cleanup removes the keeper, fetch containers and volume. Host-level stale-resource cleanup is still required after a machine crash.

Inventory supports exact registry requirements, npm package-lock v1-3 (including actual alias names), Pipenv, Poetry 2.0/2.1 and uv v1, and a bounded CycloneDX 1.5/1.6 JSON subset with exact PyPI/npm purls. Unsupported Yarn/Pnpm/Bun, direct URL/Git/path dependencies, unknown schemas and incomplete components fail closed. Platform/marker alternatives are queried rather than evaluated on the worker. No repository code, installer, build script or hook runs during extraction.

Poll the existing scan GET endpoint for durable report.stage/progress/completed_steps/updated_at. Completion is 100 only after final findings commit. Every update rechecks lease and current authorization; bounded SSE is implemented as documented below. See PHASE_1_3_STATUS.md for current real-tool and container evidence and outstanding GitHub acceptance.


## Default core-only image

The default image now uses the official native Semgrep 1.182.1 engine directly. semgrep-artifact.lock pins the wheel hash used solely to extract native files; requirements.lock pins seven Python packages for Bandit. The historical legacy-full-cli.snapshot records the old 69-package full frontend and is not installed by the current Dockerfile. Explicit JSON targets cover .py/.pyi, .js/.jsx/.mjs/.cjs and .ts/.tsx for the bundled Python/JavaScript/TypeScript rules, avoid argument expansion limits, and ignore repository ignore files. Unknown rule languages, engine version mismatch, errors, skipped targets or excessive findings/output fail closed. No Semgrep Python frontend, MCP server or OpenTelemetry SDK is installed in the final image. Native vendored libraries still need separate vulnerability assessment.

scripts/audit_scanner_dependencies.py assesses the seven runtime packages and native artifact metadata; CI runs it. The historical two-advisory frontend audit is retained separately. Current zero OSV references do not establish a vulnerability-free image. Actual minimal-image package/version/absence checks and all-tool containment tests passed; see scanner-core-image-results.json, docker-scanner-results.json and docker-test-results.xml.


Scanner cleanup continuation: the stale-resource janitor now recognizes generated source-keeper container names while retaining exact ownership, resource-kind and two-hour minimum-age checks. Nine unit cases pass. Five actual Docker recovery checks pass in scanner-recovery-live-results.json, including dry-run preservation, stale owned keeper/volume removal, recent/unowned preservation, idempotency and final synthetic-fixture cleanup. The opt-in scripts/verify_scanner_recovery.py driver scopes discovery to its generated resources and is included in CI. This does not simulate a host crash.


## Scan history and remediation reporting

GET /api/v1/repositories/{repository_id}/scans retains its list response and accepts status (queued/running/completed/failed/dead_letter/cancelled), requested_by (UUID), sort_by (created_at/attempts/status), direction (asc/desc), limit and offset. Defaults remain creation ascending; every sort uses ID ascending to break ties. Filters never broaden tenant/repository authorization.

POST /api/v1/scans/{job_id}/cancel requires repository.scan and repository management access. Queued/running jobs become cancelled and lose their lease; late workers cannot commit findings. Repeats on a cancelled job return 200 without duplicate cancellation audits. Completed/dead-letter jobs return 409; unauthorized roles return 403 and inaccessible jobs/repositories return 404. Active isolated tool processes are not synchronously killed: the worker stops at its next progress/authorization check or tool timeout. The API never gains access to Docker.

GET /api/v1/repositories/{repository_id}/remediation requires finding.read and repository access. Response fields are groups, total_groups, limit, offset and counting="finding_observations". Each scanner/rule/severity group includes open, triaged, resolved, false_positive, total, first_observed_at and last_observed_at. Groups sort by scanner/rule/severity; limit/offset are bounded by the shared API contract. Filters: scanner, severity and observed_since (ISO 8601 with explicit timezone). Naive timestamps and unknown filter values return 422. Unauthorized roles return 403 and inaccessible repository IDs return 404. Reads are audited without source contents or credentials.

These are counts of retained observations and current analyst dispositions. Repeat scans can count the same vulnerability repeatedly. Observation timestamps are not resolution timestamps; resolved is an analyst decision, not proof of a clean rescan. No deduplication or fix-time/SLA claim is made. The query groups in SQL and paginates groups; it does not load full finding histories into API memory. Non-empty pages share a single query snapshot; an empty offset page uses a separate count query and may reflect concurrent writes.


Installed Debian source-package assessment is now complete for the current scanner/backend images, with 69 advisory matches per image and no listed Debian 13 fixed versions in the retrieved records. This is a failed clean-image gate, not security signoff. Vendored native libraries remain outside coverage. See SCANNER_DEPENDENCY_RISKS.md and the image audit JSON files.


## Bounded scan SSE

GET /api/v1/scans/{job_id}/events uses Authorization and X-Organization-ID headers; never put bearer tokens in URLs. Use a streaming fetch client that can supply headers. Only repository.read with current repository access may subscribe. One active stream per member/organization across jobs is enforced atomically in Redis; a second receives 429/Retry-After 30, Redis failure receives 503. Streams use no-store and X-Accel-Buffering:no.

event:scan carries the current ScanOutput JSON with a SHA256 snapshot ID. Unchanged snapshots produce comment heartbeats. This is latest-state delivery, not an ordered/replayable event log; Last-Event-ID is not a resume guarantee. Reconnect after the bounded 30-second window. Terminal statuses close after their snapshot. After headers, revoked/expired identity, membership/MFA/role/repository access, DB or Redis failure yields a generic event:end without another snapshot. Polling is every two seconds; each read uses a fresh transaction that closes before yielding. Slow dependencies may extend wall time; ordinary request/database timeouts still apply. Disconnects release the lease; a 60-second renewable expiry recovers abandoned leases. Revocation may race a previously authorized in-flight snapshot, as with ordinary HTTP; every next update rechecks.

scripts/verify_scan_stream.py runs real password-protected loopback Redis and in-process ASGI with synthetic authentication/in-memory SQLite. Six gates verify admission, stale-owner release safety, snapshot delivery, cleanup and outage denial. It is not real Supabase authentication or network HTTP acceptance. Regression tests separately cover expiry, session/membership/role/repository revocation, heartbeats and disconnects.
