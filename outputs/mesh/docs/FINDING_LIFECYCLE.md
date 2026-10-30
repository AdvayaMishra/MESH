# Finding dispositions and history

PATCH /api/v1/findings/{id} now accepts open, investigating, confirmed, false_positive, resolved and accepted_risk. The previous triaged value remains supported for compatibility. Existing repository management authorization applies. Repeating the same current status is a no-op.

Each actual change adds an explicit append-only audit record carrying before/after status in its action and the responsible user/time in the audit fields. The existing generic domain event is retained. GET /api/v1/findings/{id}/history returns typed, paginated transitions after checking tenant and repository read access. Earlier generic audits do not reveal before/after states; missing history is not fabricated.

Finding filters and remediation observation groups support all dispositions. Investigating, confirmed, triaged and accepted_risk remain unresolved exposure for unified code risk. Accepted risk is a human disposition, not removal of the underlying vulnerability. Resolved and false_positive are excluded from unresolved exposure, but these analyst dispositions do not establish independently verified fix timing.

Existing reports count finding observations. Separate [finding identity APIs](FINDING_IDENTITIES.md) group exact recorded metadata across scans and retain each observation and its decisions. Semantic equivalence and independently verified remediation remain pending.
