import type { ChainNode, CloudResource, Finding, Incident, Repo } from "@/lib/types";

export const repos: Repo[] = [
  { name: "atlas-console-web", language: "TypeScript", health: 88, coverage: 81, openFindings: 4, lastScan: "2026-10-23T06:40:00Z", authorized: true, projectId: "PRJ-01" },
  { name: "atlas-telemetry-api", language: "Go", health: 79, coverage: 74, openFindings: 6, lastScan: "2026-10-23T06:42:00Z", authorized: true, projectId: "PRJ-01" },
  { name: "orbit-portal", language: "TypeScript", health: 64, coverage: 58, openFindings: 11, lastScan: "2026-10-22T21:10:00Z", authorized: true, projectId: "PRJ-02" },
  { name: "pulse-pipeline", language: "Python", health: 83, coverage: 77, openFindings: 5, lastScan: "2026-10-23T05:55:00Z", authorized: true, projectId: "PRJ-03" },
  { name: "pulse-dashboards", language: "TypeScript", health: 85, coverage: 72, openFindings: 0, lastScan: "2026-10-23T05:58:00Z", authorized: true, projectId: "PRJ-03" },
  { name: "forge-pipelines", language: "Python", health: 72, coverage: 66, openFindings: 7, lastScan: "2026-10-22T23:30:00Z", authorized: true, projectId: "PRJ-04" },
  { name: "sentry-access-broker", language: "Rust", health: 94, coverage: 90, openFindings: 1, lastScan: "2026-10-23T07:20:00Z", authorized: true, projectId: "PRJ-05" },
  { name: "lumen-ui", language: "TypeScript", health: 91, coverage: 85, openFindings: 2, lastScan: "2026-10-21T12:00:00Z", authorized: false, projectId: "PRJ-06" },
];

export const findings: Finding[] = [
  { id: "F-2041", title: "SQL query built from unsanitised request parameter", severity: "critical", scanner: "Semgrep", repo: "orbit-portal", file: "src/server/invoices/search.ts", line: 58, evidence: "const q = `SELECT * FROM invoices WHERE customer = '${req.query.customer}'`", remediation: "Use parameterised queries or the ORM's query builder. Never interpolate request data into SQL strings.", status: "In progress", assignee: "LR-1021", cwe: "CWE-89", detectedAt: "2026-10-22T21:12:00Z" },
  { id: "F-2042", title: "Hardcoded API credential committed to repository", severity: "critical", scanner: "Gitleaks", repo: "forge-pipelines", file: "ci/deploy_staging.py", line: 14, evidence: "Credential matched rule 'generic-api-key' — value redacted [REDACTED:••••••••3f9a]", remediation: "Rotate the credential immediately, move it to the secrets vault, and purge it from git history.", status: "Open", assignee: "LR-1024", cwe: "CWE-798", detectedAt: "2026-10-22T23:34:00Z" },
  { id: "F-2043", title: "Dependency with known remote code execution (RCE) flaw", severity: "high", scanner: "OSV", repo: "atlas-telemetry-api", file: "go.mod", line: 23, evidence: "github.com/example/yamlparse v1.4.2 — affected by OSV-2026-0412, fixed in 1.4.6", remediation: "Upgrade to 1.4.6 or later and run the integration tests for the config loader.", status: "Open", assignee: "LR-1011", cwe: "CWE-502", detectedAt: "2026-10-23T06:44:00Z" },
  { id: "F-2044", title: "Use of subprocess with shell=True", severity: "high", scanner: "Bandit", repo: "forge-pipelines", file: "ci/build_helpers.py", line: 102, evidence: "subprocess.run(cmd, shell=True)  # cmd includes branch name", remediation: "Pass arguments as a list and set shell=False. Validate branch names against an allow-list.", status: "In progress", assignee: "LR-1024", cwe: "CWE-78", detectedAt: "2026-10-22T23:35:00Z" },
  { id: "F-2045", title: "Missing authorization check on invoice download", severity: "high", scanner: "Semgrep", repo: "orbit-portal", file: "src/server/invoices/download.ts", line: 31, evidence: "Handler reads invoiceId from params without verifying ownership", remediation: "Verify the invoice belongs to the authenticated customer before streaming the file.", status: "In progress", assignee: "LR-1021", cwe: "CWE-639", detectedAt: "2026-10-22T21:13:00Z" },
  { id: "F-2046", title: "Weak hash function used for cache keys", severity: "medium", scanner: "Bandit", repo: "pulse-pipeline", file: "pipeline/cache.py", line: 44, evidence: "hashlib.md5(payload).hexdigest()", remediation: "Use SHA-256 (hashlib.sha256) for cache keys; add usedforsecurity=False only if not security relevant.", status: "Open", assignee: "LR-1022", cwe: "CWE-327", detectedAt: "2026-10-23T05:58:00Z" },
  { id: "F-2047", title: "Cross-site scripting through dangerouslySetInnerHTML", severity: "medium", scanner: "Semgrep", repo: "atlas-console-web", file: "src/components/AlertBanner.tsx", line: 27, evidence: "<div dangerouslySetInnerHTML={{ __html: alert.message }} />", remediation: "Render alert text as plain text or sanitise with a vetted HTML sanitiser.", status: "Open", assignee: "LR-1020", cwe: "CWE-79", detectedAt: "2026-10-23T06:41:00Z" },
  { id: "F-2048", title: "Prototype pollution in lodash.merge", severity: "high", scanner: "OSV", repo: "orbit-portal", file: "package.json", line: 41, evidence: "lodash 4.17.15 — affected by OSV-2020-0521, fixed in 4.17.21", remediation: "Upgrade lodash to 4.17.21 or replace merge calls with structuredClone.", status: "Fixed", assignee: "LR-1062", cwe: "CWE-1321", detectedAt: "2026-10-12T09:00:00Z" },
  { id: "F-2049", title: "Private key material found in test fixtures", severity: "critical", scanner: "Gitleaks", repo: "sentry-access-broker", file: "tests/fixtures/dev_key.pem", line: 1, evidence: "Private key header detected — body redacted [REDACTED:PEM block, 1,704 chars]", remediation: "Delete the file, regenerate fixtures at test time, and rotate any key that was ever deployed.", status: "Fixed", assignee: "LR-1031", cwe: "CWE-321", detectedAt: "2026-10-09T14:20:00Z" },
  { id: "F-2050", title: "Insecure random number generator for session IDs", severity: "medium", scanner: "Bandit", repo: "pulse-pipeline", file: "pipeline/session.py", line: 19, evidence: "random.randint(0, 10**9)", remediation: "Use the secrets module (secrets.token_urlsafe) for session identifiers.", status: "Open", assignee: "LR-1022", cwe: "CWE-330", detectedAt: "2026-10-23T05:59:00Z" },
  { id: "F-2051", title: "Container image runs as root", severity: "low", scanner: "Semgrep", repo: "forge-pipelines", file: "Dockerfile", line: 3, evidence: "No USER instruction found before ENTRYPOINT", remediation: "Create a non-root user and switch with the USER instruction.", status: "Open", assignee: "LR-1012", detectedAt: "2026-10-22T23:36:00Z" },
  { id: "F-2052", title: "Outdated TLS configuration allows TLS 1.0", severity: "low", scanner: "Semgrep", repo: "atlas-telemetry-api", file: "internal/server/tls.go", line: 12, evidence: "MinVersion: tls.VersionTLS10", remediation: "Set MinVersion to tls.VersionTLS12 or later.", status: "Accepted risk", assignee: "LR-1011", cwe: "CWE-326", detectedAt: "2026-10-15T08:45:00Z" },
];

export const vulnTrend = [
  { week: "W37", critical: 5, high: 11, medium: 17, low: 9 },
  { week: "W38", critical: 4, high: 12, medium: 16, low: 9 },
  { week: "W39", critical: 4, high: 10, medium: 15, low: 8 },
  { week: "W40", critical: 3, high: 10, medium: 14, low: 8 },
  { week: "W41", critical: 3, high: 8, medium: 14, low: 7 },
  { week: "W42", critical: 2, high: 8, medium: 12, low: 7 },
  { week: "W43", critical: 2, high: 7, medium: 12, low: 6 },
];

export const scanHistory = [
  { id: "SCN-882", repo: "sentry-access-broker", at: "2026-10-23T07:20:00Z", duration: "1m 12s", findings: 1, scanners: ["Semgrep", "Gitleaks", "OSV"], status: "Completed" },
  { id: "SCN-881", repo: "atlas-telemetry-api", at: "2026-10-23T06:42:00Z", duration: "2m 03s", findings: 6, scanners: ["Semgrep", "Gitleaks", "OSV"], status: "Completed" },
  { id: "SCN-880", repo: "atlas-console-web", at: "2026-10-23T06:40:00Z", duration: "1m 48s", findings: 4, scanners: ["Semgrep", "Gitleaks", "OSV"], status: "Completed" },
  { id: "SCN-879", repo: "pulse-pipeline", at: "2026-10-23T05:55:00Z", duration: "1m 31s", findings: 5, scanners: ["Bandit", "Semgrep", "OSV"], status: "Completed" },
  { id: "SCN-878", repo: "forge-pipelines", at: "2026-10-22T23:30:00Z", duration: "2m 22s", findings: 7, scanners: ["Bandit", "Semgrep", "Gitleaks", "OSV"], status: "Completed" },
  { id: "SCN-877", repo: "lumen-ui", at: "2026-10-21T12:00:00Z", duration: "0m 41s", findings: 0, scanners: ["Semgrep"], status: "Authorization revoked" },
];

export const dependencyRisk = [
  { name: "Vulnerable", value: 14, color: "#FF6B8A" },
  { name: "Outdated", value: 41, color: "#FFB547" },
  { name: "Healthy", value: 318, color: "#00C9A7" },
];

export const incidents: Incident[] = [
  { id: "INC-3021", title: "Possible account takeover followed by large database export", severity: "critical", status: "Investigating", detectedAt: "2026-10-23T02:14:00Z", summary: "A sequence of correlated signals on one service account suggests credential misuse. This is a signal for investigation, not confirmation of malicious intent.", assets: ["prod-orders-db", "api-gateway", "svc-reporting"], analyst: "LR-1030", riskBefore: 34, riskAfter: 71, chainId: "chain-1" },
  { id: "INC-3022", title: "Public storage bucket exposes build artifacts", severity: "high", status: "Open", detectedAt: "2026-10-22T18:30:00Z", summary: "An S3 bucket used for CI artifacts allows public read access. No access from unknown IPs has been observed yet.", assets: ["s3://lumen-ci-artifacts"], analyst: "LR-1031", riskBefore: 28, riskAfter: 46 },
  { id: "INC-3023", title: "API request rate 9× baseline from partner integration", severity: "medium", status: "Contained", detectedAt: "2026-10-22T09:05:00Z", summary: "Partner API key triggered rate limiting. Traffic pattern matches a misconfigured retry loop.", assets: ["api-gateway"], analyst: "LR-1031", riskBefore: 22, riskAfter: 26 },
  { id: "INC-3024", title: "Privilege change outside change window", severity: "high", status: "Investigating", detectedAt: "2026-10-21T22:48:00Z", summary: "An IAM role gained admin permissions at 22:48 UTC without a linked change request.", assets: ["iam:role/ops-deploy"], analyst: "LR-1030", riskBefore: 30, riskAfter: 52 },
  { id: "INC-3019", title: "Outdated TLS endpoint on staging gateway", severity: "low", status: "Resolved", detectedAt: "2026-10-18T13:10:00Z", summary: "Staging gateway accepted TLS 1.0. Configuration updated and verified.", assets: ["staging-gateway"], analyst: "LR-1031", riskBefore: 24, riskAfter: 21 },
];

export const attackChain: ChainNode[] = [
  { id: "n1", label: "Unusual login", detail: "svc-reporting signed in from a new ASN and country", at: "2026-10-23T01:42:00Z", severity: "medium", risk: 8, source: "Identity", evidence: ["Login from AS64500 (new for this account)", "Country change: IN → NL within 4h", "MFA not required for service account"] },
  { id: "n2", label: "New device", detail: "First-seen device fingerprint registered", at: "2026-10-23T01:49:00Z", severity: "medium", risk: 9, source: "Identity", evidence: ["Device fingerprint not previously seen", "Browser automation signature detected", "Registered 7 minutes after login"] },
  { id: "n3", label: "API abuse", detail: "Burst of 4,820 requests across reporting endpoints", at: "2026-10-23T01:58:00Z", severity: "high", risk: 14, source: "API", evidence: ["Requests per minute: 9× the 30-day baseline", "Sequential enumeration of /v2/reports/{id}", "Rate limit hit 11 times"] },
  { id: "n4", label: "Privilege escalation", detail: "Role changed to db-reader-admin", at: "2026-10-23T02:03:00Z", severity: "high", risk: 17, source: "IAM", evidence: ["Role binding added outside change window", "No linked change request", "Actor: svc-reporting (self-granted)"] },
  { id: "n5", label: "Database access", detail: "Queries against customers and orders tables", at: "2026-10-23T02:09:00Z", severity: "high", risk: 15, source: "Database", evidence: ["First access to customers table by this identity", "Full-table SELECT on orders (2.1M rows)", "Query executed via new device"] },
  { id: "n6", label: "Large download", detail: "1.8 GB export to an external endpoint", at: "2026-10-23T02:14:00Z", severity: "critical", risk: 22, source: "Network", evidence: ["Outbound transfer 1.8 GB over 3 minutes", "Destination not on approved list", "Egress alert fired but not blocked (monitor mode)"] },
];

export const riskComponents = [
  { name: "Identity", score: 72, weight: 18, trend: +6 },
  { name: "Behavior", score: 58, weight: 14, trend: +4 },
  { name: "Network", score: 41, weight: 12, trend: +1 },
  { name: "API", score: 67, weight: 14, trend: +9 },
  { name: "Privileges", score: 63, weight: 16, trend: +5 },
  { name: "Data access", score: 54, weight: 12, trend: +3 },
  { name: "Cloud posture", score: 38, weight: 8, trend: -2 },
  { name: "Code security", score: 33, weight: 6, trend: -4 },
];

export const riskTrend = [
  { day: "Oct 10", score: 27 }, { day: "Oct 11", score: 26 }, { day: "Oct 12", score: 29 },
  { day: "Oct 13", score: 28 }, { day: "Oct 14", score: 30 }, { day: "Oct 15", score: 31 },
  { day: "Oct 16", score: 29 }, { day: "Oct 17", score: 32 }, { day: "Oct 18", score: 31 },
  { day: "Oct 19", score: 30 }, { day: "Oct 20", score: 33 }, { day: "Oct 21", score: 41 },
  { day: "Oct 22", score: 48 }, { day: "Oct 23", score: 55 },
];

export const riskChangeLog = [
  { at: "2026-10-23T02:14:00Z", delta: +7, reason: "Large external download correlated into INC-3021" },
  { at: "2026-10-22T18:30:00Z", delta: +6, reason: "Public storage bucket detected (INC-3022)" },
  { at: "2026-10-21T22:48:00Z", delta: +8, reason: "Out-of-window privilege change (INC-3024)" },
  { at: "2026-10-18T13:30:00Z", delta: -3, reason: "Staging TLS endpoint remediated" },
];

export const loginActivity = Array.from({ length: 24 }, (_, h) => ({
  hour: `${String(h).padStart(2, "0")}:00`,
  logins: [4, 3, 6, 3, 2, 2, 5, 12, 38, 61, 72, 69, 54, 66, 71, 64, 52, 33, 18, 11, 8, 6, 5, 4][h],
  anomalous: [0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 0, 0][h] + (h === 1 ? 2 : 0),
}));

export const apiUsage = Array.from({ length: 14 }, (_, i) => ({
  day: `Oct ${10 + i}`,
  requests: [182, 190, 176, 188, 195, 120, 110, 198, 204, 192, 201, 207, 214, 396][i],
  baseline: 190,
}));

export const deviceTimeline = [
  { at: "2026-10-23T01:49:00Z", who: "svc-reporting", what: "New device registered (automation signature)", level: "high" as const },
  { at: "2026-10-22T08:12:00Z", who: "Ishaan Bhatt", what: "Second laptop enrolled — approved by IT ticket #4471", level: "info" as const },
  { at: "2026-10-21T21:30:00Z", who: "Ishaan Bhatt", what: "Login from managed device outside usual hours", level: "medium" as const },
  { at: "2026-10-19T10:04:00Z", who: "Yuki Tanaka", what: "First device enrolled during onboarding", level: "info" as const },
];

export const downloadAnomalies = [
  { who: "svc-reporting", volume: "1.8 GB", baseline: "40 MB", dest: "External · unapproved", level: "critical" as const },
  { who: "Marcus Chen", volume: "640 MB", baseline: "90 MB", dest: "Personal cloud storage", level: "medium" as const },
  { who: "Ishaan Bhatt", volume: "210 MB", baseline: "120 MB", dest: "Internal repo mirror", level: "low" as const },
];

export const employeeRiskDistribution = [
  { band: "0–20", count: 15, color: "#00C9A7" },
  { band: "21–40", count: 6, color: "#38BDF8" },
  { band: "41–60", count: 2, color: "#FFB547" },
  { band: "61–80", count: 1, color: "#FF8A3D" },
  { band: "81–100", count: 0, color: "#FF6B8A" },
];

export const cloudResources: CloudResource[] = [
  { id: "R-901", name: "lumen-ci-artifacts", provider: "AWS", type: "S3 bucket", region: "ap-south-1", risk: "high", issue: "Public read access enabled", owner: "LR-1024" },
  { id: "R-902", name: "ops-deploy", provider: "AWS", type: "IAM role", region: "global", risk: "high", issue: "AdministratorAccess attached outside change window", owner: "LR-1012" },
  { id: "R-903", name: "orders-prod-db", provider: "AWS", type: "RDS PostgreSQL", region: "ap-south-1", risk: "medium", issue: "Not encrypted with a customer-managed key", owner: "LR-1011" },
  { id: "R-904", name: "reports-sql", provider: "Azure", type: "SQL database", region: "centralindia", risk: "medium", issue: "Firewall allows 0.0.0.0/0 on port 1433", owner: "LR-1011" },
  { id: "R-905", name: "pulse-events", provider: "GCP", type: "Pub/Sub topic", region: "asia-south1", risk: "low", issue: "Message retention above policy (14d)", owner: "LR-1022" },
  { id: "R-906", name: "gke-forge-runners", provider: "GCP", type: "GKE cluster", region: "asia-south1", risk: "medium", issue: "Node pool exposes SSH to the internet", owner: "LR-1012" },
  { id: "R-907", name: "svc-reporting", provider: "AWS", type: "IAM user", region: "global", risk: "critical", issue: "Long-lived access key, no MFA, wildcard S3 access", owner: "LR-1011" },
  { id: "R-908", name: "sentry-broker-vm", provider: "Azure", type: "Virtual machine", region: "centralindia", risk: "low", issue: "OS patch level 14 days behind", owner: "LR-1031" },
];

export const cloudPosture = { score: 74, byProvider: [{ name: "AWS", score: 69 }, { name: "Azure", score: 76 }, { name: "GCP", score: 82 }] };
