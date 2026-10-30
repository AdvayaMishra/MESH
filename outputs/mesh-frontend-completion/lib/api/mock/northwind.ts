import { makeDataset, type RawDataset } from "@/lib/api/dataset";
import { TRUST_START, clampScore, isTrustEligible } from "@/lib/trust";
import { northwindComplaints, northwindPromotions } from "@/lib/api/mock/hr-seed";
import type { ChainNode, CloudResource, Employee, Finding, Incident, Project, Repo, Task, TrustEvent } from "@/lib/types";

/**
 * Simulated tenant #2 — "Northwind Health Labs" (synthetic; no real company). Different people, projects, tasks, repos,
 * findings, incidents, finance and notifications from tenant #1 so switching organizations visibly changes every view.
 */
const ORG = { name: "Northwind Health Labs", domain: "northwindhealth.example", plan: "Business", region: "Toronto, CA" };
type PR = RawDataset["pullRequests"][number];

const ev = (id: string, date: string, delta: number, reason: string, source: string, reviewedBy?: string): TrustEvent => ({ id, date, delta, reason, source, reviewedBy });
type Seed = Omit<Employee, "trustEvents" | "trustScore" | "email" | "location" | "salaryBand"> & { trustEvents?: TrustEvent[]; target?: number };

const seeds: Seed[] = [
  { id: "NH-2001", name: "Rebecca Thornton", role: "Founder & CEO", appRole: "owner", department: "Finance", status: "Active", verification: "Verified", joinDate: "2018-05-14", projects: [], riskScore: 7 },
  { id: "NH-2002", name: "Omar Haddad", role: "People & Culture Lead", appRole: "hr", department: "People Ops", status: "Active", verification: "Verified", joinDate: "2019-11-04", manager: "NH-2001", projects: [], riskScore: 10 },
  { id: "NH-2010", name: "Lena Fischer", role: "Principal Engineer", appRole: "senior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2019-02-18", manager: "NH-2001", projects: ["NPJ-01", "NPJ-03"], riskScore: 15, target: 35,
    trustEvents: [ev("nt1", "2026-10-12", 3, "Led reviewed migration with zero rollbacks", "DevTrack", "Omar Haddad"), ev("nt2", "2026-09-20", -1, "Late security review sign-off on one release", "DevTrack", "Omar Haddad")] },
  { id: "NH-2011", name: "Kenji Watanabe", role: "Senior Backend Engineer", appRole: "senior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2020-08-03", manager: "NH-2010", projects: ["NPJ-01", "NPJ-02"], riskScore: 19, target: 32 },
  { id: "NH-2012", name: "Amara Nwosu", role: "Staff SRE", appRole: "senior-dev", department: "Infrastructure", status: "Active", verification: "Verified", joinDate: "2020-01-27", manager: "NH-2001", projects: ["NPJ-04"], riskScore: 24, target: 40 },
  { id: "NH-2020", name: "Theo Larsen", role: "Software Engineer II", appRole: "junior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2024-03-11", manager: "NH-2010", projects: ["NPJ-01", "NPJ-05"], riskScore: 12, target: 27,
    trustEvents: [ev("nt3", "2026-10-16", 2, "Proposal NPJ-06 approved with positive reviewer notes", "DevTrack", "Lena Fischer")] },
  { id: "NH-2021", name: "Zara Malik", role: "Software Engineer I", appRole: "junior-dev", department: "Engineering", status: "Probation", verification: "Verified", joinDate: "2026-06-08", manager: "NH-2011", projects: ["NPJ-02"], riskScore: 21, target: 20 },
  { id: "NH-2022", name: "Mateus Rocha", role: "Frontend Engineer", appRole: "junior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2023-10-02", manager: "NH-2010", projects: ["NPJ-01", "NPJ-05"], riskScore: 17, target: 29 },
  { id: "NH-2023", name: "Ingrid Solberg", role: "QA Engineer", appRole: "junior-dev", department: "Engineering", status: "On leave", verification: "Verified", joinDate: "2022-04-19", manager: "NH-2011", projects: ["NPJ-02"], riskScore: 9, target: 25 },
  { id: "NH-2030", name: "Hassan Qureshi", role: "Security Lead", appRole: "security-analyst", department: "Security", status: "Active", verification: "Verified", joinDate: "2020-09-14", manager: "NH-2001", projects: ["NPJ-04"], riskScore: 5, target: 43 },
  { id: "NH-2031", name: "Chloe Dubois", role: "Application Security Engineer", appRole: "security-analyst", department: "Security", status: "Active", verification: "Verified", joinDate: "2023-01-09", manager: "NH-2030", projects: ["NPJ-04"], riskScore: 8, target: 34 },
  { id: "NH-2040", name: "Sana Patel", role: "Head of Product", appRole: "hr", department: "Product", status: "Active", verification: "Verified", joinDate: "2021-03-22", manager: "NH-2001", projects: ["NPJ-05"], riskScore: 11 },
  { id: "NH-2041", name: "Viktor Novak", role: "Product Designer", appRole: "junior-dev", department: "Design", status: "Active", verification: "Verified", joinDate: "2024-05-13", manager: "NH-2040", projects: ["NPJ-05"], riskScore: 13 },
  { id: "NH-2050", name: "Grace Adeyemi", role: "Finance Manager", appRole: "hr", department: "Finance", status: "Active", verification: "Verified", joinDate: "2022-07-18", manager: "NH-2001", projects: [], riskScore: 14 },
  { id: "NH-2060", name: "Diego Alvarez", role: "Enterprise Account Executive", appRole: "junior-dev", department: "Sales", status: "Active", verification: "Verified", joinDate: "2023-02-06", manager: "NH-2001", projects: [], riskScore: 18 },
  { id: "NH-2071", name: "Mei Lin", role: "Data Engineer", appRole: "junior-dev", department: "Engineering", status: "Onboarding", verification: "Pending review", joinDate: "2026-10-12", manager: "NH-2011", projects: [], riskScore: 0 },
];

const employees: Employee[] = seeds.map((s) => {
  const { target, ...rest } = s;
  let trustScore: number | null = null;
  let trustEvents: TrustEvent[] = [];
  if (isTrustEligible(rest)) {
    const listed = rest.trustEvents ?? [];
    const gap = (target ?? TRUST_START) - TRUST_START - listed.reduce((a, e) => a + e.delta, 0);
    trustEvents = [...listed];
    if (gap !== 0) trustEvents.push({ id: `${rest.id}-agg`, date: "2026-09-01", delta: gap, reason: "Aggregated reviewed contributions before September 2026", source: "DevTrack", reviewedBy: "Performance review" });
    trustEvents.push({ id: `${rest.id}-start`, date: rest.joinDate, delta: 0, reason: "Starting score for eligible role: 20 / 50 (2 stars)", source: "System" });
    trustScore = clampScore(TRUST_START + trustEvents.reduce((a, e) => a + e.delta, 0));
  }
  return {
    ...rest,
    email: `${rest.name.toLowerCase().replace(/[^a-z ]/g, "").replace(/ /g, ".")}@${ORG.domain}`,
    location: ["Toronto", "Montréal", "Remote — Oslo", "Remote — Lagos", "Vancouver", "Remote — Lisbon"][parseInt(rest.id.slice(-2), 10) % 6],
    salaryBand: rest.department === "Engineering" || rest.department === "Infrastructure" ? "Band N3" : rest.department === "Security" ? "Band N-S2" : "Band N-G2",
    trustScore,
    trustEvents,
  };
});

const c = (id: string, author: string, at: string, text: string) => ({ id, author, at, text });

const projects: Project[] = [
  { id: "NPJ-01", key: "CARE", name: "CareLink Patient Portal", description: "Patient-facing portal for appointments, results and secure messaging.", status: "Active", priority: "High", progress: 64, lead: "NH-2010", members: ["NH-2010", "NH-2011", "NH-2020", "NH-2022"], budget: 310000, spent: 189000, department: "Engineering", dueDate: "2027-01-22", cloud: "Azure", repos: ["carelink-web", "carelink-api"] },
  { id: "NPJ-02", key: "LABS", name: "LabBridge HL7 Gateway", description: "Gateway that normalises lab results from partner clinics into one schema.", status: "At risk", priority: "Critical", progress: 41, lead: "NH-2011", members: ["NH-2011", "NH-2021", "NH-2023"], budget: 175000, spent: 139000, department: "Engineering", dueDate: "2026-12-04", cloud: "AWS", repos: ["labbridge-gateway"] },
  { id: "NPJ-03", key: "VITAL", name: "Vitals Streaming Pipeline", description: "Streaming ingestion for wearable vitals with anomaly flags for clinicians.", status: "Active", priority: "Medium", progress: 78, lead: "NH-2010", members: ["NH-2010", "NH-2071"], budget: 140000, spent: 101000, department: "Engineering", dueDate: "2026-11-30", cloud: "GCP", repos: ["vitals-stream"] },
  { id: "NPJ-04", key: "SHIELD", name: "Shield PHI Access Controls", description: "Break-glass access, field-level encryption and access reviews for patient data.", status: "Active", priority: "Critical", progress: 55, lead: "NH-2030", members: ["NH-2030", "NH-2031", "NH-2012"], budget: 120000, spent: 66000, department: "Security", dueDate: "2027-02-10", cloud: "Azure", repos: ["shield-access"] },
  { id: "NPJ-05", key: "ATLAS", name: "Northwind Design Language", description: "Accessible component library for all clinical and patient apps.", status: "Completed", priority: "Low", progress: 100, lead: "NH-2040", members: ["NH-2040", "NH-2041", "NH-2022", "NH-2020"], budget: 52000, spent: 49000, department: "Product", dueDate: "2026-09-26", cloud: "GCP", repos: ["nw-design-kit"] },
  { id: "NPJ-06", key: "TRIAGE", name: "Triage Assistant (rules-based)", description: "Rules-based symptom triage helper for nurses, with full audit trail.", status: "Awaiting approval", priority: "High", progress: 0, lead: "NH-2020", members: ["NH-2020"], budget: 64000, spent: 0, department: "Engineering", dueDate: "2027-03-15", proposedBy: "NH-2020", proposedAt: "2026-10-16", cloud: "Azure", repos: [] },
  { id: "NPJ-07", key: "AUDITX", name: "Consent & Audit Exporter", description: "Export of patient-consent and access-audit records for compliance reviews.", status: "Awaiting approval", priority: "Medium", progress: 0, lead: "NH-2022", members: ["NH-2022", "NH-2011"], budget: 38000, spent: 0, department: "Engineering", dueDate: "2027-01-08", proposedBy: "NH-2022", proposedAt: "2026-10-21", cloud: "AWS", repos: [] },
];

const tasks: Task[] = [
  { id: "T-1", key: "CARE-210", title: "Appointment reschedule flow with conflict checks", description: "Prevent double-booking when patients reschedule from the portal.", status: "In progress", priority: "High", assignee: "NH-2020", projectId: "NPJ-01", points: 5, labels: ["frontend"], sprint: "Sprint 12", due: "2026-10-30", comments: [c("c1", "NH-2010", "2026-10-22T09:10:00Z", "Please include the clinic timezone in the conflict check.")] },
  { id: "T-2", key: "CARE-211", title: "Secure message attachments with virus scan", description: "Scan uploads before they reach clinicians.", status: "In review", priority: "Critical", assignee: "NH-2011", projectId: "NPJ-01", points: 8, labels: ["backend", "security"], sprint: "Sprint 12", due: "2026-10-28", comments: [] },
  { id: "T-3", key: "CARE-212", title: "Accessible results table (WCAG 2.2 AA)", description: "Keyboard and screen-reader support for lab result tables.", status: "To do", priority: "Medium", assignee: "NH-2022", projectId: "NPJ-01", points: 3, labels: ["frontend", "a11y"], sprint: "Sprint 13", due: "2026-11-10", comments: [] },
  { id: "T-4", key: "LABS-31", title: "Map LOINC codes for partner clinic B", description: "Normalise clinic B result codes to the shared schema.", status: "In progress", priority: "Critical", assignee: "NH-2021", projectId: "NPJ-02", points: 5, labels: ["backend"], sprint: "Sprint 12", due: "2026-10-29", comments: [c("c2", "NH-2011", "2026-10-23T08:00:00Z", "Pair with me before merging; clinic B sends legacy codes.")] },
  { id: "T-5", key: "LABS-32", title: "Retry queue for failed HL7 deliveries", description: "Dead-letter queue with bounded retries.", status: "To do", priority: "High", assignee: "NH-2011", projectId: "NPJ-02", points: 5, labels: ["backend"], sprint: "Sprint 13", due: "2026-11-06", comments: [] },
  { id: "T-6", key: "VITAL-55", title: "Backfill anomaly thresholds for wearables", description: "Recompute thresholds from the last 90 days.", status: "Done", priority: "Medium", assignee: "NH-2071", projectId: "NPJ-03", points: 3, labels: ["data"], sprint: "Sprint 12", due: "2026-10-21", comments: [] },
  { id: "T-7", key: "SHIELD-9", title: "Break-glass access with mandatory justification", description: "Time-boxed emergency access to PHI with reviewer notification.", status: "In progress", priority: "Critical", assignee: "NH-2031", projectId: "NPJ-04", points: 8, labels: ["security"], sprint: "Sprint 12", due: "2026-11-03", comments: [] },
  { id: "T-8", key: "SHIELD-10", title: "Quarterly access review report", description: "Generate per-department access review exports.", status: "Backlog", priority: "Low", assignee: "NH-2012", projectId: "NPJ-04", points: 2, labels: ["compliance"], sprint: "Sprint 14", due: "2026-11-24", comments: [] },
  { id: "T-9", key: "CARE-213", title: "Rate limit login and password reset endpoints", description: "Protect patient accounts from credential stuffing.", status: "To do", priority: "High", assignee: "NH-2020", projectId: "NPJ-01", points: 3, labels: ["backend", "security"], sprint: "Sprint 12", due: "2026-10-31", comments: [] },
];

const sprints = [
  { id: "Sprint 11", start: "2026-09-28", end: "2026-10-09", status: "Completed", velocity: 38 },
  { id: "Sprint 12", start: "2026-10-12", end: "2026-10-23", status: "Active", velocity: 33 },
  { id: "Sprint 13", start: "2026-10-26", end: "2026-11-06", status: "Planned", velocity: 0 },
  { id: "Sprint 14", start: "2026-11-09", end: "2026-11-20", status: "Planned", velocity: 0 },
];

const pullRequests: PR[] = [
  { id: "#301", title: "Appointment reschedule conflict checks", repo: "carelink-web", author: "NH-2020", reviewers: ["NH-2010"], status: "Open", checks: "passing", additions: 204, deletions: 33, updatedAt: "2026-10-23T09:00:00Z", taskKey: "CARE-210" },
  { id: "#298", title: "Attachment virus scanning", repo: "carelink-api", author: "NH-2011", reviewers: ["NH-2010", "NH-2031"], status: "Approved", checks: "passing", additions: 166, deletions: 18, updatedAt: "2026-10-23T07:40:00Z", taskKey: "CARE-211" },
  { id: "#77", title: "Clinic B LOINC mapping", repo: "labbridge-gateway", author: "NH-2021", reviewers: ["NH-2011"], status: "Changes requested", checks: "failing", additions: 98, deletions: 6, updatedAt: "2026-10-22T16:10:00Z", taskKey: "LABS-31" },
  { id: "#41", title: "Break-glass access flow", repo: "shield-access", author: "NH-2031", reviewers: ["NH-2030"], status: "Open", checks: "running", additions: 350, deletions: 41, updatedAt: "2026-10-23T10:15:00Z", taskKey: "SHIELD-9" },
];

const repos: Repo[] = [
  { name: "carelink-web", language: "TypeScript", health: 84, coverage: 76, openFindings: 3, lastScan: "2026-10-23T06:10:00Z", authorized: true, projectId: "NPJ-01" },
  { name: "carelink-api", language: "Kotlin", health: 71, coverage: 68, openFindings: 6, lastScan: "2026-10-23T06:14:00Z", authorized: true, projectId: "NPJ-01" },
  { name: "labbridge-gateway", language: "Java", health: 59, coverage: 52, openFindings: 9, lastScan: "2026-10-22T20:00:00Z", authorized: true, projectId: "NPJ-02" },
  { name: "vitals-stream", language: "Python", health: 86, coverage: 79, openFindings: 2, lastScan: "2026-10-23T05:30:00Z", authorized: true, projectId: "NPJ-03" },
  { name: "shield-access", language: "Rust", health: 93, coverage: 88, openFindings: 1, lastScan: "2026-10-23T07:00:00Z", authorized: true, projectId: "NPJ-04" },
  { name: "nw-design-kit", language: "TypeScript", health: 90, coverage: 83, openFindings: 1, lastScan: "2026-10-18T09:00:00Z", authorized: false, projectId: "NPJ-05" },
];

const fnd = (id: string, title: string, severity: Finding["severity"], scanner: Finding["scanner"], repo: string, file: string, line: number, evidence: string, remediation: string, status: Finding["status"], assignee: string, detectedAt: string, cwe?: string): Finding =>
  ({ id, title, severity, scanner, repo, file, line, evidence, remediation, status, assignee, detectedAt, cwe });
const findings: Finding[] = [
  fnd("F-710", "Patient lookup concatenates user input into SQL", "critical", "Semgrep", "labbridge-gateway", "src/main/java/lookup/PatientDao.java", 88, "String q = \"SELECT * FROM patients WHERE mrn='\" + mrn + \"'\"", "Use prepared statements with bound parameters.", "Open", "NH-2011", "2026-10-21T10:00:00Z", "CWE-89"),
  fnd("F-711", "API token committed in deployment script", "critical", "Gitleaks", "carelink-api", "deploy/release.sh", 9, "Credential matched rule 'generic-api-key' — value redacted [REDACTED:••••••••b17c]", "Rotate the token, move it to the secrets manager and purge history.", "In progress", "NH-2031", "2026-10-22T08:30:00Z", "CWE-798"),
  fnd("F-712", "Deserialisation of untrusted HL7 payload", "high", "Semgrep", "labbridge-gateway", "src/main/java/hl7/Parser.java", 140, "new ObjectInputStream(request.getInputStream()).readObject()", "Replace native deserialisation with a schema-validated parser.", "Open", "NH-2021", "2026-10-20T14:00:00Z", "CWE-502"),
  fnd("F-713", "Dependency with known remote code execution flaw", "high", "OSV", "carelink-api", "build.gradle.kts", 41, "log-lib 2.14.1 — affected by OSV-2026-0771, fixed in 2.17.2", "Upgrade to 2.17.2 or later.", "Open", "NH-2011", "2026-10-19T09:00:00Z"),
  fnd("F-714", "Weak hash used for session cache keys", "medium", "Bandit", "vitals-stream", "stream/cache.py", 52, "hashlib.sha1(payload).hexdigest()", "Use SHA-256 for cache keys.", "Open", "NH-2071", "2026-10-18T12:00:00Z", "CWE-328"),
  fnd("F-715", "Cross-site scripting in results banner", "medium", "Semgrep", "carelink-web", "src/components/ResultBanner.tsx", 31, "<div dangerouslySetInnerHTML={{ __html: msg }} />", "Render as text or sanitise with a vetted library.", "In progress", "NH-2022", "2026-10-17T15:00:00Z", "CWE-79"),
  fnd("F-716", "Private key in test fixtures", "critical", "Gitleaks", "shield-access", "tests/fixtures/dev.pem", 1, "Private key header detected — body redacted [REDACTED:PEM block, 1,675 chars]", "Delete, regenerate fixtures at test time, rotate the key.", "Fixed", "NH-2031", "2026-10-15T08:00:00Z"),
  fnd("F-717", "Container runs as root", "low", "Semgrep", "labbridge-gateway", "Dockerfile", 4, "No USER instruction before ENTRYPOINT", "Add a non-root USER.", "Accepted risk", "NH-2012", "2026-10-14T11:00:00Z"),
];

const incidents: Incident[] = [
  { id: "INC-5101", title: "Repeated failed logins then success on a clinician account", severity: "high", status: "Investigating", detectedAt: "2026-10-23T03:05:00Z", summary: "A burst of failed logins followed by a successful sign-in from a new location. A signal for investigation, not confirmation of misuse.", assets: ["idp:clinician-portal"], analyst: "NH-2030", riskBefore: 20, riskAfter: 44, chainId: "chain-1" },
  { id: "INC-5102", title: "Storage container with patient exports readable by link", severity: "critical", status: "Open", detectedAt: "2026-10-22T20:10:00Z", summary: "An Azure blob container holding de-identified exports allows anonymous read. Review whether any identifiers remain.", assets: ["azure://nw-exports"], analyst: "NH-2031", riskBefore: 25, riskAfter: 58 },
  { id: "INC-5103", title: "Partner clinic sending 6× normal HL7 volume", severity: "medium", status: "Contained", detectedAt: "2026-10-21T11:00:00Z", summary: "Partner retry loop; rate limiting engaged and the partner has been notified.", assets: ["labbridge-gateway"], analyst: "NH-2031", riskBefore: 18, riskAfter: 14 },
  { id: "INC-5098", title: "TLS 1.0 enabled on internal staging", severity: "low", status: "Resolved", detectedAt: "2026-10-12T09:00:00Z", summary: "Staging load balancer updated to TLS 1.2 minimum and verified.", assets: ["staging-lb"], analyst: "NH-2030", riskBefore: 19, riskAfter: 16 },
];

const attackChain: ChainNode[] = [
  { id: "n1", label: "Failed login burst", detail: "47 failed sign-ins on one clinician account", at: "2026-10-23T02:31:00Z", severity: "medium", risk: 7, source: "Identity", evidence: ["47 failures in 6 minutes", "Source: residential proxy range", "Lockout threshold not reached"] },
  { id: "n2", label: "Successful login", detail: "Sign-in from a first-seen country", at: "2026-10-23T02:38:00Z", severity: "medium", risk: 9, source: "Identity", evidence: ["Country change CA → RO", "MFA satisfied via SMS", "New browser fingerprint"] },
  { id: "n3", label: "Bulk record search", detail: "Sequential patient lookups", at: "2026-10-23T02:52:00Z", severity: "high", risk: 13, source: "API", evidence: ["312 lookups in 9 minutes", "Outside the clinician's assigned clinic", "Break-glass not invoked"] },
  { id: "n4", label: "Export request", detail: "CSV export of 1,900 records requested", at: "2026-10-23T03:05:00Z", severity: "high", risk: 15, source: "Application", evidence: ["Export size 8× the user's norm", "Export blocked pending review"] },
];

const riskComponents = [
  { name: "Identity", score: 61, weight: 18, trend: +5 }, { name: "Behavior", score: 49, weight: 14, trend: +2 },
  { name: "Network", score: 36, weight: 12, trend: 0 }, { name: "API", score: 57, weight: 14, trend: +6 },
  { name: "Privileges", score: 44, weight: 16, trend: +1 }, { name: "Data access", score: 66, weight: 12, trend: +7 },
  { name: "Cloud posture", score: 52, weight: 8, trend: +3 }, { name: "Code security", score: 41, weight: 6, trend: -1 },
];

const cr = (id: string, name: string, provider: CloudResource["provider"], type: string, region: string, risk: CloudResource["risk"], issue: string, owner: string): CloudResource => ({ id, name, provider, type, region, risk, issue, owner });
const cloudResources: CloudResource[] = [
  cr("R-31", "nw-exports", "Azure", "Blob container", "canadacentral", "critical", "Anonymous read access enabled", "NH-2012"),
  cr("R-32", "clinician-idp", "Azure", "Identity tenant", "global", "high", "SMS accepted as second factor", "NH-2030"),
  cr("R-33", "labbridge-db", "AWS", "RDS PostgreSQL", "ca-central-1", "medium", "Backup retention below policy", "NH-2011"),
  cr("R-34", "vitals-topic", "GCP", "Pub/Sub topic", "northamerica-northeast1", "low", "Message retention above policy", "NH-2071"),
  cr("R-35", "gke-ci", "GCP", "GKE cluster", "northamerica-northeast1", "medium", "Public control-plane endpoint", "NH-2012"),
];

export const northwind = makeDataset({
  id: "northwind",
  simulatedLabel: "Simulated · Healthcare SaaS",
  org: ORG,
  approvalHistory: { "NPJ-05": [{ id: "nh1", at: "2026-06-20T10:00:00Z", by: "Rebecca Thornton", action: "Approved", note: "Accessibility library unblocks every product team." }] },
  roleUsers: { owner: "NH-2001", hr: "NH-2002", "senior-dev": "NH-2010", "junior-dev": "NH-2020", "security-analyst": "NH-2030" },
  monthlyCost: [
    { month: "Apr", actual: 61200, forecast: 61200 }, { month: "May", actual: 63900, forecast: 63900 }, { month: "Jun", actual: 66100, forecast: 66100 },
    { month: "Jul", actual: 70400, forecast: 70400 }, { month: "Aug", actual: 72800, forecast: 72800 }, { month: "Sep", actual: 76500, forecast: 76500 },
    { month: "Oct", actual: 79800, forecast: 79800 }, { month: "Nov", actual: null, forecast: 83100 }, { month: "Dec", actual: null, forecast: 86400 }, { month: "Jan", actual: null, forecast: 89200 },
  ],
  providerSplit: [{ name: "AWS", value: 21400, color: "#635BFF" }, { name: "Azure", value: 41900, color: "#38BDF8" }, { name: "GCP", value: 16500, color: "#00C9A7" }],
  utilization: [{ service: "Compute", used: 63, reserved: 80 }, { service: "Storage", used: 71, reserved: 85 }, { service: "Databases", used: 66, reserved: 78 }, { service: "Network", used: 39, reserved: 55 }, { service: "Kubernetes", used: 58, reserved: 74 }],
  orgKpis: { totalEmployees: 16, employeeDelta: 1, activeProjects: 3, projectDelta: 0, monthlyCloudSpend: 79800, spendDelta: 4.3, pendingApprovals: 2, openIncidents: 3, incidentDelta: 1, securityPosture: 71, postureDelta: -2 },
  kpiSparks: { employees: [12, 12, 13, 14, 14, 15, 16], projects: [2, 2, 3, 3, 3, 3, 3], spend: [61, 64, 66, 70, 73, 77, 80], approvals: [0, 1, 1, 2, 1, 2, 2], incidents: [2, 2, 3, 2, 3, 3, 3], posture: [78, 77, 76, 75, 74, 73, 71] },
  whatIfPrompts: ["What if we move LabBridge to reserved instances?", "Which department has the highest infrastructure cost?", "Which projects need additional resources?"],
  whatIfScenarios: {
    "What if we move LabBridge to reserved instances?": {
      headline: "Reserved capacity could save about $4.1k per month",
      summary: "Committing LabBridge's steady-state compute to one-year reserved instances lowers monthly spend from $79.8k to roughly $75.7k, at the cost of flexibility if the gateway is re-architected.",
      assumptions: ["One-year no-upfront term", "Steady load over the last 90 days", "No change in partner volume"],
      series: [{ label: "Nov", baseline: 83100, scenario: 78900 }, { label: "Dec", baseline: 86400, scenario: 82200 }, { label: "Jan", baseline: 89200, scenario: 85000 }, { label: "Feb", baseline: 91800, scenario: 87600 }],
      impact: [{ label: "Monthly savings", value: "$4.1k", tone: "mint" }, { label: "Commitment", value: "12 months", tone: "amber" }, { label: "Flexibility", value: "Reduced", tone: "amber" }, { label: "Risk", value: "Low", tone: "mint" }],
    },
    "Which department has the highest infrastructure cost?": {
      headline: "Engineering leads at $34.6k, 43% of cloud spend",
      summary: "Engineering carries the most spend, driven by CareLink and LabBridge environments. Security follows at $12.2k, mostly logging retention for PHI access audits.",
      assumptions: ["Allocation by resource tags", "Untagged resources (4%) assigned to Engineering"],
      series: [{ label: "Eng", baseline: 34600, scenario: 37000 }, { label: "Infra", baseline: 18900, scenario: 21000 }, { label: "Security", baseline: 12200, scenario: 14000 }, { label: "Product", baseline: 5400, scenario: 7000 }],
      impact: [{ label: "Top department", value: "Engineering", tone: "violet" }, { label: "Share of spend", value: "43%", tone: "violet" }, { label: "Budget used", value: "94%", tone: "amber" }, { label: "Audit log cost", value: "$6.3k", tone: "coral" }],
    },
    "Which projects need additional resources?": {
      headline: "LabBridge is the clear resourcing gap",
      summary: "LabBridge has spent 79% of budget at 41% progress against a December deadline. Adding one backend engineer for six weeks closes most of the gap.",
      assumptions: ["Burn rate over the last 4 sprints", "Capacity includes approved leave"],
      series: [{ label: "LabBridge", baseline: 41, scenario: 66 }, { label: "CareLink", baseline: 64, scenario: 70 }, { label: "Vitals", baseline: 78, scenario: 80 }, { label: "Shield", baseline: 55, scenario: 60 }],
      impact: [{ label: "Projects at risk", value: "1", tone: "coral" }, { label: "Suggested capacity", value: "+1 FTE", tone: "violet" }, { label: "LabBridge budget used", value: "79%", tone: "amber" }, { label: "Priority", value: "Critical", tone: "coral" }],
    },
  },
  departmentStats: [
    { dept: "Engineering", headcount: 7, cloudSpend: 34600, budget: 36800 }, { dept: "Infrastructure", headcount: 1, cloudSpend: 18900, budget: 21000 },
    { dept: "Security", headcount: 2, cloudSpend: 12200, budget: 15000 }, { dept: "Product", headcount: 1, cloudSpend: 5400, budget: 7500 },
    { dept: "Design", headcount: 1, cloudSpend: 1900, budget: 3000 }, { dept: "Sales", headcount: 1, cloudSpend: 1200, budget: 2500 },
  ],
  projects, tasks, sprints, pullRequests, repos, findings,
  vulnTrend: [
    { week: "W37", critical: 3, high: 8, medium: 12, low: 6 }, { week: "W38", critical: 3, high: 9, medium: 12, low: 6 }, { week: "W39", critical: 4, high: 9, medium: 11, low: 5 },
    { week: "W40", critical: 4, high: 8, medium: 11, low: 5 }, { week: "W41", critical: 3, high: 7, medium: 10, low: 5 }, { week: "W42", critical: 3, high: 7, medium: 10, low: 4 }, { week: "W43", critical: 3, high: 6, medium: 9, low: 4 },
  ],
  scanHistory: [
    { id: "SCN-410", repo: "shield-access", at: "2026-10-23T07:00:00Z", duration: "0m 58s", findings: 1, scanners: ["Semgrep", "Gitleaks", "OSV"], status: "Completed" },
    { id: "SCN-409", repo: "carelink-api", at: "2026-10-23T06:14:00Z", duration: "2m 10s", findings: 6, scanners: ["Semgrep", "Gitleaks", "OSV"], status: "Completed" },
    { id: "SCN-408", repo: "carelink-web", at: "2026-10-23T06:10:00Z", duration: "1m 40s", findings: 3, scanners: ["Semgrep", "Gitleaks", "OSV"], status: "Completed" },
    { id: "SCN-407", repo: "labbridge-gateway", at: "2026-10-22T20:00:00Z", duration: "3m 02s", findings: 9, scanners: ["Semgrep", "OSV", "Gitleaks"], status: "Completed" },
    { id: "SCN-406", repo: "nw-design-kit", at: "2026-10-18T09:00:00Z", duration: "0m 33s", findings: 0, scanners: ["Semgrep"], status: "Authorization revoked" },
  ],
  dependencyRisk: [{ name: "Vulnerable", value: 9, color: "#FF6B8A" }, { name: "Outdated", value: 27, color: "#FFB547" }, { name: "Healthy", value: 204, color: "#00C9A7" }],
  incidents, attackChain, riskComponents,
  riskTrend: [
    { day: "Oct 10", score: 31 }, { day: "Oct 11", score: 30 }, { day: "Oct 12", score: 32 }, { day: "Oct 13", score: 33 }, { day: "Oct 14", score: 33 }, { day: "Oct 15", score: 35 },
    { day: "Oct 16", score: 34 }, { day: "Oct 17", score: 36 }, { day: "Oct 18", score: 36 }, { day: "Oct 19", score: 37 }, { day: "Oct 20", score: 39 }, { day: "Oct 21", score: 43 }, { day: "Oct 22", score: 50 }, { day: "Oct 23", score: 54 },
  ],
  riskChangeLog: [
    { at: "2026-10-23T03:05:00Z", delta: +4, reason: "Export request after bulk lookups correlated into INC-5101" },
    { at: "2026-10-22T20:10:00Z", delta: +7, reason: "Anonymous-read storage container detected (INC-5102)" },
    { at: "2026-10-12T09:30:00Z", delta: -3, reason: "Staging TLS configuration remediated" },
  ],
  loginActivity: Array.from({ length: 24 }, (_, h) => ({ hour: `${String(h).padStart(2, "0")}:00`, logins: [2, 1, 3, 2, 1, 2, 6, 14, 30, 44, 51, 49, 38, 47, 52, 46, 35, 20, 11, 7, 5, 4, 3, 2][h], anomalous: h === 2 ? 3 : h === 3 ? 1 : 0 })),
  apiUsage: Array.from({ length: 14 }, (_, i) => ({ day: `Oct ${10 + i}`, requests: [96, 101, 94, 99, 104, 61, 58, 102, 107, 103, 109, 111, 118, 214][i], baseline: 100 })),
  deviceTimeline: [
    { at: "2026-10-23T02:38:00Z", who: "clinician account", what: "New browser fingerprint on first-seen country login", level: "high" as const },
    { at: "2026-10-21T15:00:00Z", who: "Theo Larsen", what: "Second laptop enrolled — approved by IT ticket #812", level: "info" as const },
    { at: "2026-10-12T10:00:00Z", who: "Mei Lin", what: "First device enrolled during onboarding", level: "info" as const },
  ],
  downloadAnomalies: [
    { who: "clinician account", volume: "1,900 records", baseline: "210 records", dest: "CSV export · blocked", level: "critical" as const },
    { who: "Diego Alvarez", volume: "180 MB", baseline: "60 MB", dest: "Personal cloud storage", level: "medium" as const },
  ],
  employeeRiskDistribution: [{ band: "0–20", count: 12, color: "#00C9A7" }, { band: "21–40", count: 3, color: "#38BDF8" }, { band: "41–60", count: 1, color: "#FFB547" }, { band: "61–80", count: 0, color: "#FF8A3D" }, { band: "81–100", count: 0, color: "#FF6B8A" }],
  dbAccess: [
    { table: "patients", rows: 312, who: "clinician account", tone: "coral" },
    { table: "lab_results", rows: 1900, who: "clinician account", tone: "coral" },
    { table: "appointments", rows: 5400, who: "Theo Larsen", tone: "amber" },
    { table: "audit_log", rows: 740, who: "Hassan Qureshi", tone: "mint" },
  ],
  cloudResources, cloudPosture: { score: 68, byProvider: [{ name: "AWS", score: 72 }, { name: "Azure", score: 61 }, { name: "GCP", score: 74 }] },
  payrollSummary: {
    month: "October 2026", gross: 238400, net: 191700, taxes: 33900, benefits: 12800, headcount: 16,
    trend: [{ month: "May", gross: 214000 }, { month: "Jun", gross: 219500 }, { month: "Jul", gross: 224100 }, { month: "Aug", gross: 228800 }, { month: "Sep", gross: 233200 }, { month: "Oct", gross: 238400 }],
    byDept: [{ dept: "Engineering", amount: 104200 }, { dept: "Infrastructure", amount: 31800 }, { dept: "Security", amount: 38900 }, { dept: "Product", amount: 22400 }, { dept: "Sales", amount: 17100 }, { dept: "Finance", amount: 13200 }, { dept: "People Ops", amount: 10800 }],
    discrepancies: [
      { id: "D-1", employee: "NH-2021", issue: "Probation pro-ration differs from contract by $286", suggestion: "Check the probation end date" },
      { id: "D-2", employee: "NH-2071", issue: "Relocation allowance missing from onboarding checklist", suggestion: "Add it if the offer letter includes it" },
    ],
  },
  idSubmissions: [
    { id: "V-71", employee: "NH-2071", submittedAt: "2026-10-22T14:00:00Z", docType: "Government photo ID", status: "Pending review" as const,
      submitted: { name: "Mei Lin", dob: "1997-07-09", idNumber: "••••••5520", expiry: "2030-03-14" },
      ocr: { name: "MEI LIN", dob: "1997-07-09", idNumber: "••••••5520", expiry: "2030-03-14" }, confidence: { name: 0.99, dob: 0.96, idNumber: 0.92, expiry: 0.94 }, history: [] as { at: string; by: string; action: string; note: string }[] },
  ],
  leaveRequests: [
    { id: "L-1", employee: "NH-2023", type: "Medical leave", from: "2026-10-05", to: "2026-11-13", days: 29, status: "Approved" },
    { id: "L-2", employee: "NH-2022", type: "Annual leave", from: "2026-12-14", to: "2026-12-24", days: 8, status: "Pending" },
    { id: "L-3", employee: "NH-2060", type: "Casual leave", from: "2026-10-30", to: "2026-10-30", days: 1, status: "Pending" },
  ],
  employees,
  complaints: northwindComplaints,
  promotions: northwindPromotions,
  notifications: [
    { id: "N-1", title: "Critical incident INC-5102", body: "Storage container with exports allows anonymous read.", at: "2026-10-22T20:15:00Z", module: "VADER", read: false, href: "/vader/incidents/INC-5102", tone: "coral" },
    { id: "N-2", title: "2 projects awaiting your approval", body: "Triage Assistant and Consent & Audit Exporter need a decision.", at: "2026-10-23T08:00:00Z", module: "Owner", read: false, href: "/owner/projects", tone: "violet" },
    { id: "N-3", title: "ID submitted by Mei Lin", body: "OCR is ready for human review.", at: "2026-10-22T14:05:00Z", module: "People", read: false, href: "/people/verification", tone: "mint" },
    { id: "N-4", title: "Gitleaks finding in carelink-api", body: "A credential pattern was detected and redacted.", at: "2026-10-22T08:35:00Z", module: "DevTrack", read: true, href: "/devtrack/security", tone: "amber" },
    { id: "N-5", title: "Scan authorization revoked for nw-design-kit", body: "Re-authorize the repository to resume scans.", at: "2026-10-18T09:00:00Z", module: "DevTrack", read: true, href: "/devtrack/security", tone: "sky" },
  ],
  activity: [
    { id: "A-1", at: "2026-10-23T09:30:00Z", actor: "Lena Fischer", text: "approved Theo Larsen's pull request in carelink-web", module: "DevTrack" as const },
    { id: "A-2", at: "2026-10-23T08:50:00Z", actor: "Hassan Qureshi", text: "opened investigation on INC-5101", module: "VADER" as const },
    { id: "A-3", at: "2026-10-22T16:00:00Z", actor: "Omar Haddad", text: "approved medical leave for Ingrid Solberg", module: "People" as const },
    { id: "A-4", at: "2026-10-21T15:20:00Z", actor: "Consent & Audit Exporter", text: "was submitted for approval by Mateus Rocha", module: "Owner" as const },
  ],
  auditLog: [
    { id: "AU-4001", at: "2026-10-23T09:40:00Z", actor: "Rebecca Thornton", action: "Viewed financial overview", target: "Owner · Cloud spend", module: "Owner", result: "Success", ip: "198.51.100.14" },
    { id: "AU-4000", at: "2026-10-23T08:50:00Z", actor: "Hassan Qureshi", action: "Opened incident", target: "INC-5101", module: "VADER", result: "Success", ip: "10.40.2.18" },
    { id: "AU-3999", at: "2026-10-22T20:12:00Z", actor: "System", action: "Flagged public storage container", target: "nw-exports", module: "VADER", result: "Simulated", ip: "—" },
    { id: "AU-3998", at: "2026-10-22T16:02:00Z", actor: "Omar Haddad", action: "Approved leave request", target: "L-1 Ingrid Solberg", module: "People", result: "Success", ip: "10.40.2.9" },
    { id: "AU-3997", at: "2026-10-21T15:19:00Z", actor: "Mateus Rocha", action: "Submitted project proposal", target: "NPJ-07", module: "DevTrack", result: "Success", ip: "10.40.3.31" },
  ],
});
