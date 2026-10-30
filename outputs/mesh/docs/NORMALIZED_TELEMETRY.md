# Normalized telemetry context

Migrations 0016/0017 add bounded JSON context and an organization/category/time index to security_events, then protect security_events and anomalies against UPDATE. Runtime UPDATE/direct DELETE are revoked. The existing narrowly granted retention function remains the only runtime deletion path and continues to preserve incident and risk-assessment evidence. All 51 application tables retain forced RLS and browser denial. Existing observations have an empty context; historical source/device metadata is not inferred.

Event categories now include authentication, session, device, api, privilege, database, file, download, repository, cloud, cloud_audit, network and behavior. Existing category meanings and immutable tenant/source receipts remain. Reusing a source ID with changed metadata or core fields returns 409; null optional context values are canonicalized away. Actor/session/resource IDs remain tenant-scoped correlation identifiers.

Optional context fields:

- source: enumerated kind, bounded collector name and numeric version. Names describe the submitter's claim; they are not verified integrations.
- reported_severity: info/low/medium/high/critical. This does not directly set anomaly weights or risk scores.
- ip: optional uppercase two-letter country code, bounded ASN and pseudonymous address object. Address objects require a 64-character lowercase digest, method hmac-sha256 and a nonsecret key identifier. Raw IP strings and arbitrary IP fields are rejected.
- device: optional HMAC fingerprint, enumerated OS family, strict Boolean new_device and managed flags. Raw user-agent/device dumps are rejected.
- attributes: enumerated operation, data classification, bounded transferred-byte count, strict permission-change Boolean, repository action and cloud service. Arbitrary log/password/document attributes are rejected.

Collectors must perform HMAC generation and privacy filtering before ingestion, using securely configured tenant-specific rotating keys. Keys never belong in telemetry payloads. MESH validates the digest shape/method claim but cannot prove a submitted digest was generated correctly. API output labels context provenance reported_unverified. Country, device flags, classifications and source names remain reported observations, not verified identity, geography, device management or employment evidence.

New deterministic advisory signals cover reported successful revoked-session use (weight 25), new-device flags (15), file volume above 500 (20), repository volume above 100 or successful admin/branch-protection changes (25), and cloud-audit volume above 100 or successful root/logging/admin-policy activity (30). Thresholds and Boolean signal switches are organization configurable. Accepted signal explanations explicitly say they are not proof of malicious activity. Volume baselines now also support file/network/repository/cloud_audit; 20 prior nonsynthetic observations and nonzero variance are required. Synthetic and real evidence remain separate.

Unified risk maps session to identity, device to behavior, file to data access, repository to code security and cloud audit to cloud posture. The existing documented weighting/coverage formula and immutable historical snapshots remain. One source event is still scored once, using its highest anomaly weight. Reported severity alone does not override this formula.

GET /api/v1/vader/events accepts all category filters plus source_kind and reported_severity, under tenant/analyst authorization. Full typed request/output schemas are in OpenAPI. Context is not sent to AI; AI summaries still accept only bounded aggregate numbers.

This implements normalization, validation, storage, filters, detection and correlation for supplied events. It does not install device agents or claim collection from arbitrary networks, repositories or cloud accounts. Actual authorized collectors and evaluated detection quality remain separate work. HMAC metadata can still be sensitive; configure retention/privacy policies explicitly.
