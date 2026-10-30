# Debian image advisory review

`scripts/review_debian_security.py --assessment docs/backend-debian-audit.json --output docs/backend-debian-security-review.json` enriches an existing complete installed-image assessment with the official Debian Security Tracker. Repeat for scanner/OCR assessments. The command downloads one bounded HTTPS JSON dataset, records its decoded SHA256/time/source, binds findings to the installed source-package name/version and Debian release, and retains the assessed immutable image ID. Exit zero means review generation completed, never that an image is cleared.

The existing `audit_debian_image.py` remains the clean-image gate and fails on advisory matches. Review output never suppresses a match, mutates its source assessment, waives risk or provides independent deployment approval. Missing records, unsupported releases, undetermined status and malformed entries remain explicit review cases. A fixed version in another Debian release cannot clear the installed release.

The 26 October review retains all findings:

| Image | Retained | Upstream open | Upstream reports not affected | Undetermined |
|---|---:|---:|---:|---:|
| Backend | 69 | 67 | 1 | 1 |
| Scanner | 69 | 67 | 1 | 1 |
| OCR | 212 | 206 | 3 | 3 |

Backend/scanner records contain 26 `unimportant` and 43 unassigned urgency labels. OCR records contain 85 `unimportant`, two `low` and 125 unassigned labels. These are upstream labels, not application exploitability assessments. No resolved nonzero fixed version was listed for these matched release records. The `fixed_version=0` records are preserved as upstream not-affected evidence for human review, without automatically overriding OSV or clearing the gate.

A separate disposable-container check refreshed signed Debian repository indexes and simulated an upgrade. It found only a `tzdata` update from `2026c-0+deb13u1` to `2026e-0+deb13u1`. The installed dpkg database remained byte-identical. No packages, source image or host configuration were changed, and this unrelated available update is not presented as a fix for the advisory matches. The report records the exact inspected image; rerun after changing an image.

Remaining security work is concrete: review binary/library reachability and native/vendor coverage, evaluate upstream fixes when available, rebuild pinned images when an applicable fix exists, repeat compatibility/containment/service acceptance, and obtain independent security review. Production security clearance remains false. There is no blanket exemption for nonroot containers or low-urgency findings.

Evidence: `backend-debian-security-review.json`, `scanner-debian-security-review.json`, `ocr-debian-security-review.json`, and `debian-update-availability-results.json`. Unit tests cover source/release binding, missing/malformed evidence, limits, redirects and preservation of every finding.

Primary references: [Debian Security Tracker](https://security-tracker.debian.org/tracker/), [Debian tracker JSON](https://security-tracker.debian.org/tracker/data/json), and [Debian's APT advisory notes](https://security-tracker.debian.org/tracker/CVE-2011-3374). Source-package matches alone do not prove that a particular vulnerable binary path is reachable in MESH.

For the retained backend/scanner SQLite discrepancy, [CVE-2026-39113](https://security-tracker.debian.org/tracker/CVE-2026-39113) explicitly reports vulnerable code never present in a Debian released version. This supports the recorded upstream-not-affected classification for that single match; it does not resolve the other matches or replace native-library assessment.
