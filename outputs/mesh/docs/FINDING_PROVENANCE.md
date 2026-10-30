# Finding provenance and dependency context

New scan findings retain the successful scan job ID and exact immutable commit SHA. A database foreign key binds organization, repository, scan and commit together. Partial provenance and mismatched tenant/repository/commit references are rejected. Historical findings retain null provenance; no job or commit is guessed from timestamps.

Where scanners report a start column, it is retained as a positive one-based position. Bandit zero-based offsets are converted; unavailable columns remain unknown. Evidence, code snippets, secrets and arbitrary scanner prose remain excluded.

OSV batch responses are matched to the exact query through every pagination step. Findings retain only package name, ecosystem and pinned version alongside advisory ID. Repeated identical advisory observations for one package/version are deduplicated within the response; different packages or versions are not merged. This is not cross-scan semantic vulnerability identity tracking.

OSV locations remain `dependency-manifest` because the current dependency inventory does not retain an exact manifest-file occurrence. No source filename is invented. OSV batch IDs are not CVSS enrichment: `info` is a display placeholder, not proof that the advisory has low security impact.

Repository finding queries support `scan_job_id`, exact 40-character `commit_sha` and `dependency_name`, alongside existing status/scanner/severity filters and stable sorting. All remain subject to tenant and repository access checks. A foreign scan filter cannot expose another repository's findings. Clients cannot edit provenance through the disposition API.

Migration 0022 adds nullable provenance/dependency/column fields and exact-scope constraints; it does not backfill or rewrite historical observations. The worker also fences results if the job's repository or commit changes while a scan is running.

Verification includes unit/API cases, real PostgreSQL constraint tests, hosted rollback-only query/constraint checks, and actual read-only OSV queries. The live verifier sends only public package triples (plus required pagination tokens), never checkout source or credentials. See osv-provenance-live-results.json. Real GitHub App checkout/webhook acceptance remains unverified without its authorized configuration.
