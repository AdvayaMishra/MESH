# Private identity OCR

Migration 0015 extends the existing forced-RLS identity document table. Employee uploads still require a clean malware verdict, validated PNG/JPEG, a maximum 2 MiB and 10 million pixels, and private Supabase Storage. OCR never approves an employee or changes verification status.

Build `docker build -f security-engine/OCR.Dockerfile -t mesh-ocr:local .` using a clean source context. The base image is digest pinned; the Tesseract and English data package versions are pinned and downloaded through signed Debian package metadata. Transitive OS versions are recorded by the image assessment, rather than fully reproducible per-artifact locks.

Set `DOCUMENT_OCR_ENABLED=true`, an independently generated Fernet `DOCUMENT_OCR_KEY`, and `DOCUMENT_OCR_IMAGE` in protected backend/worker configuration. Use a secret manager or a protected local environment file; never put the key in frontend settings, source control, images, commands or logs. Production requires a registry image pinned by SHA256 digest. Keep the same key across authorized API and OCR workers, separate from invitation encryption. Drain work and re-encrypt retained results under an explicitly reviewed rotation procedure before changing it; there is no plaintext or old-key fallback.

Run `python -m app.ocr_worker --organization <organization-uuid> --loop` only on a trusted worker host with the explicitly configured absolute Docker executable and a dedicated Linux Docker daemon. Use restricted runtime database credentials and verified TLS. The API does not receive a Docker socket. Tenant-bound worker credentials must have only that tenant's operational access; database context settings are not a substitute for trusted server control. Existing maintenance removes expired images and ciphertext.

The worker claims one document with a three-minute lease, commits before Storage/engine I/O, checks the stored SHA256 against downloaded bytes, and retries transient/invalid results at most three times with backoff. It rechecks organization, membership, employment, expiry, document state and lease before saving. Manual review/offboarding/expiry prevents late results from being applied. Encrypted result payloads bind document and organization IDs, so moving ciphertext between rows fails closed.

Image bytes enter the isolated container through stdin. The container has no network or host mounts, runs UID 10001 with a read-only root filesystem, no capabilities, no privilege escalation, builtin seccomp, bounded memory/no swap/CPU/PIDs, a bounded temporary filesystem and a 60-second host deadline. Persistent container logging is disabled. Only small structured suggestions return; full OCR text, addresses, government identifiers and native diagnostics are not stored or sent to AI. Only explicit `Name`/`Full Name`/`Employee Name` and `Employee ID`/`Staff ID` labels are considered. Conflicting or absent labels yield unknown values. OCR mistakes and misleading labels remain possible.

HR contracts (Bearer token plus X-Organization-ID):

- `GET /api/v1/hr/identity-documents/{id}/ocr`: nullable untrusted suggestions, HR only, audited; expired objects return 410. The employee response exposes status only.
- `POST .../{id}/ocr/retry`: requeues a failed/cancelled/unconfigured/manual document only when enabled and still pending/unexpired; resets attempt count and removes stale results.
- `POST .../{id}/ocr/manual-review`: independent HR explicitly cancels extraction and clears suggestions. The existing human decision API accepts completed/failed/unconfigured/manual review, and returns 409 while extraction is queued/running.

Statuses: not_configured, queued, running, completed, failed, cancelled, manual_review. Existing documents remain not_configured until explicitly retried. Approval/rejection remains an independent human action. A completed extraction with unknown fields is not proof of a valid ID.

Actual synthetic-English extraction evidence: ocr-live-results.json. Lease, tenant, encryption, integrity, retention and human-review regressions are in test_private_ocr.py; real PostgreSQL coverage is in test_postgres_integration.py. This does not establish real-ID accuracy, multilingual recognition, legal eligibility to process employee IDs, or production security clearance. OCR is disabled by default. The image advisory assessment currently fails; review or remediate matched advisories before approving production use.
