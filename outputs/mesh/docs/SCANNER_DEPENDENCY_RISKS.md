# Scanner dependency advisories - 24 October 2026

The live OSV assessment of all 69 frozen scanner packages found two references. That historical full-frontend audit is **failed** and retained in scanner-cli-dependency-audit.json. The current source image excludes that frontend and installs only seven Bandit Python packages plus the extracted official native core; its eight-entry runtime/artifact audit passes with zero OSV references. Actual minimal-image package absence, version checks, pip check and all-tool containment validation have passed; see scanner-core-image-results.json and docker-scanner-results.json. Runtime API dependencies are a separate 41-package inventory; the affected versions below are not installed by the API requirements lock; the API pins patched opentelemetry-api 1.45.1.

| Dependency | Advisory and upstream fix | MESH exposure and remaining work |
|---|---|---|
| mcp 1.29.0 | [Maintainer advisory GHSA-84m7-p3x7-pcfv](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-84m7-p3x7-pcfv); fixed in 1.30.0 | Stateful Streamable HTTP server session exhaustion. The current image does not install MCP or the Semgrep Python frontend. Historical full-CLI images must not be deployed. |
| opentelemetry-api 1.37.0 | [Maintainer advisory GHSA-xcq7-p3pf-p88h](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h); fixed in 1.45.1 | Unbounded inbound tracestate parsing. The current scanner image does not install OpenTelemetry Python packages. The API separately pins patched opentelemetry-api 1.45.1. |

Official PyPI metadata for latest Semgrep 1.182.1 still requires mcp==1.29.0 and opentelemetry-api/sdk/exporter ~=1.37.0, so installing the patched versions would violate its tested dependency contract. No --no-deps override, modified vendor metadata or fabricated clean audit is used. Hash freezing guarantees artifact identity, not absence of vulnerabilities.

The controls above reduce reachable attack surface; they do not remove the advisories or establish that every possible code path is safe. These historical Python dependencies are excluded from the accepted current runtime; this does not establish native-library or base-OS vulnerability coverage. Re-run scripts/audit_scanner_dependencies.py after a reviewed Semgrep upgrade, regenerate exact hashes/provenance and run all real scanner fixtures and containment tests before clearing it. Base OS packages and vendored native libraries need separate image assessment.


## Current remediation

The default source Dockerfile no longer installs the Semgrep Python distribution or its MCP/OpenTelemetry dependency tree. A build stage downloads the exact hash-verified official wheel without dependencies and extracts only native engine/library files. The final image installs the seven independently hash-locked Bandit dependencies. This avoids overriding upstream dependency requirements or altering vendor metadata. An explicit bounded JSON target adapter invokes the same pinned core, which passed actual Python/JavaScript/TypeScript trusted-fixture detection. Minimal-image build, package-absence and containment checks pass for the exact online source-built image using the verified native artifact and seven hash-locked runtime wheels. The exact default online Dockerfile build and its package/version/absence/all-tool/containment checks now pass; see scanner-source-build-results.json. Historical CLI images are not approved for deployment. Base OS and vendored native libraries remain a separate assessment scope.


## Installed Debian OS assessment — 25 October 2026

Separate from the clean Python/native-artifact package audit, the actual scanner and current offline-built backend each have 61 Debian source-package/version pairs and 69 OSV advisory matches. Both assessments complete but fail their clean-image gate. All 69 matched Debian 13 records were retrieved and none lists a fixed version; no advisory is suppressed. See scanner-debian-audit.json, backend-debian-audit.json and debian-advisory-review.json for exact package versions/IDs/image digests. Applicability review, vendor fixes and independent production security signoff remain pending. Compiled Python and vendored native-library coverage remain incomplete. CI now gates both image OS assessments.
