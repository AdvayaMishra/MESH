import type { Project, Task } from "@/lib/types";

export const projects: Project[] = [
  { id: "PRJ-01", key: "ATLAS", name: "Atlas Fleet Console", description: "Real-time fleet monitoring console for warehouse robots with live telemetry and remote commands.", status: "Active", priority: "High", progress: 72, lead: "LR-1010", members: ["LR-1010", "LR-1011", "LR-1020"], budget: 240000, spent: 168000, department: "Engineering", dueDate: "2026-12-12", cloud: "AWS", repos: ["atlas-console-web", "atlas-telemetry-api"] },
  { id: "PRJ-02", key: "ORBIT", name: "Orbit Customer Portal", description: "Self-serve portal for customers to track deployments, invoices and support tickets.", status: "At risk", priority: "High", progress: 48, lead: "LR-1010", members: ["LR-1010", "LR-1021", "LR-1062"], budget: 150000, spent: 121000, department: "Engineering", dueDate: "2026-11-28", cloud: "Azure", repos: ["orbit-portal"] },
  { id: "PRJ-03", key: "PULSE", name: "Pulse Analytics Engine", description: "Streaming analytics pipeline that powers dashboards and anomaly alerts.", status: "Active", priority: "Medium", progress: 86, lead: "LR-1011", members: ["LR-1011", "LR-1022", "LR-1023"], budget: 180000, spent: 142000, department: "Engineering", dueDate: "2026-11-15", cloud: "GCP", repos: ["pulse-pipeline", "pulse-dashboards"] },
  { id: "PRJ-04", key: "FORGE", name: "Forge CI/CD Modernisation", description: "Migrate build and deploy pipelines to ephemeral runners with signed artifacts.", status: "Active", priority: "Critical", progress: 39, lead: "LR-1012", members: ["LR-1012", "LR-1024"], budget: 120000, spent: 52000, department: "Infrastructure", dueDate: "2027-01-30", cloud: "AWS", repos: ["forge-pipelines"] },
  { id: "PRJ-05", key: "SENTRY", name: "Sentry Zero-Trust Rollout", description: "Roll out device posture checks and just-in-time access across internal tools.", status: "Active", priority: "High", progress: 61, lead: "LR-1030", members: ["LR-1030", "LR-1031", "LR-1012"], budget: 95000, spent: 58000, department: "Security", dueDate: "2026-12-20", cloud: "Azure", repos: ["sentry-access-broker"] },
  { id: "PRJ-06", key: "LUMEN", name: "Lumen Design System 2.0", description: "Unified component library and tokens shared by every customer-facing app.", status: "Completed", priority: "Low", progress: 100, lead: "LR-1040", members: ["LR-1040", "LR-1041", "LR-1022", "LR-1020"], budget: 60000, spent: 54000, department: "Product", dueDate: "2026-10-05", cloud: "GCP", repos: ["lumen-ui"] },
  { id: "PRJ-07", key: "VISTA", name: "Vista Predictive Maintenance", description: "ML-assisted predictions for robot component wear to schedule servicing earlier.", status: "Awaiting approval", priority: "High", progress: 0, lead: "LR-1020", members: ["LR-1020"], budget: 85000, spent: 0, department: "Engineering", dueDate: "2027-02-28", proposedBy: "LR-1020", proposedAt: "2026-10-18", cloud: "GCP", repos: [] },
  { id: "PRJ-08", key: "RELAY", name: "Relay Notification Service", description: "Central service for email, push and in-app notifications with per-user preferences.", status: "Awaiting approval", priority: "Medium", progress: 0, lead: "LR-1022", members: ["LR-1022", "LR-1011"], budget: 48000, spent: 0, department: "Engineering", dueDate: "2027-01-15", proposedBy: "LR-1022", proposedAt: "2026-10-20", cloud: "AWS", repos: [] },
  { id: "PRJ-09", key: "KEEP", name: "Keep Secrets Vault Migration", description: "Move application secrets to a managed vault and retire environment-file sharing.", status: "Awaiting approval", priority: "Critical", progress: 0, lead: "LR-1010", members: ["LR-1010", "LR-1024"], budget: 36000, spent: 0, department: "Infrastructure", dueDate: "2026-12-05", proposedBy: "LR-1010", proposedAt: "2026-10-21", cloud: "AWS", repos: [] },
];

export const projectById = (id: string) => projects.find((p) => p.id === id);

const c = (id: string, author: string, at: string, text: string) => ({ id, author, at, text });

export const tasks: Task[] = [
  { id: "T-1", key: "ATLAS-101", title: "Stream telemetry over WebSocket with backoff", description: "Replace polling with a resilient WebSocket client including exponential backoff and heartbeat.", status: "In progress", priority: "High", assignee: "LR-1020", projectId: "PRJ-01", points: 5, labels: ["frontend", "realtime"], sprint: "Sprint 24", due: "2026-10-29", comments: [c("c1", "LR-1010", "2026-10-21T09:12:00Z", "Please cap reconnect delay at 30s and surface a status chip in the header."), c("c2", "LR-1020", "2026-10-21T11:40:00Z", "Done on my branch, adding tests for the jitter calculation.")] },
  { id: "T-2", key: "ATLAS-102", title: "Role-based command permissions for robots", description: "Only fleet operators can send stop and reroute commands.", status: "In review", priority: "Critical", assignee: "LR-1011", projectId: "PRJ-01", points: 8, labels: ["backend", "security"], sprint: "Sprint 24", due: "2026-10-27", comments: [c("c3", "LR-1010", "2026-10-22T08:05:00Z", "Looks solid. Please add an audit entry for denied commands.")] },
  { id: "T-3", key: "ATLAS-103", title: "Map view clustering for 5k+ robots", description: "Cluster markers to keep the map responsive at scale.", status: "To do", priority: "Medium", assignee: "LR-1020", projectId: "PRJ-01", points: 5, labels: ["frontend"], sprint: "Sprint 25", due: "2026-11-06", comments: [] },
  { id: "T-4", key: "ORBIT-44", title: "Invoice PDF download endpoint", description: "Generate and stream signed PDF invoices for customers.", status: "In progress", priority: "High", assignee: "LR-1021", projectId: "PRJ-02", points: 3, labels: ["backend"], sprint: "Sprint 24", due: "2026-10-28", comments: [c("c4", "LR-1010", "2026-10-22T14:20:00Z", "Remember customers can only access their own invoices — add the ownership check.")] },
  { id: "T-5", key: "ORBIT-45", title: "Support ticket timeline component", description: "Show ticket events in a clean chronological timeline.", status: "Backlog", priority: "Low", assignee: "LR-1062", projectId: "PRJ-02", points: 2, labels: ["frontend"], sprint: "Sprint 26", due: "2026-11-20", comments: [] },
  { id: "T-6", key: "PULSE-71", title: "Backfill anomaly thresholds from last quarter", description: "Recompute dynamic thresholds using Q3 data.", status: "Done", priority: "Medium", assignee: "LR-1022", projectId: "PRJ-03", points: 3, labels: ["data"], sprint: "Sprint 24", due: "2026-10-20", comments: [] },
  { id: "T-7", key: "PULSE-72", title: "Dashboard export to CSV with row limits", description: "Allow exporting widgets while enforcing 50k row safety limit.", status: "In review", priority: "Medium", assignee: "LR-1022", projectId: "PRJ-03", points: 3, labels: ["frontend", "data"], sprint: "Sprint 24", due: "2026-10-30", comments: [] },
  { id: "T-8", key: "FORGE-12", title: "Signed build artifacts with provenance", description: "Attach SLSA-style provenance to every release build.", status: "In progress", priority: "Critical", assignee: "LR-1024", projectId: "PRJ-04", points: 8, labels: ["devops", "security"], sprint: "Sprint 24", due: "2026-11-03", comments: [c("c5", "LR-1012", "2026-10-22T10:00:00Z", "Pair on key rotation before merging.")] },
  { id: "T-9", key: "FORGE-13", title: "Ephemeral runner autoscaling policy", description: "Scale runners from 0 to 40 based on queue depth.", status: "To do", priority: "High", assignee: "LR-1012", projectId: "PRJ-04", points: 5, labels: ["devops"], sprint: "Sprint 25", due: "2026-11-12", comments: [] },
  { id: "T-10", key: "SENTRY-8", title: "Device posture check for contractor laptops", description: "Require disk encryption and OS patch level before granting access.", status: "To do", priority: "High", assignee: "LR-1031", projectId: "PRJ-05", points: 5, labels: ["security"], sprint: "Sprint 25", due: "2026-11-09", comments: [] },
  { id: "T-11", key: "ATLAS-104", title: "Fix flaky alert deduplication test", description: "Test fails intermittently on CI due to timing.", status: "Backlog", priority: "Low", assignee: "LR-1023", projectId: "PRJ-01", points: 1, labels: ["testing"], sprint: "Sprint 26", due: "2026-11-25", comments: [] },
  { id: "T-12", key: "ORBIT-46", title: "Rate limit public ticket search API", description: "Protect the search endpoint from scraping.", status: "To do", priority: "High", assignee: "LR-1021", projectId: "PRJ-02", points: 3, labels: ["backend", "security"], sprint: "Sprint 24", due: "2026-10-31", comments: [] },
];

export const sprints = [
  { id: "Sprint 23", start: "2026-09-28", end: "2026-10-09", status: "Completed", velocity: 46 },
  { id: "Sprint 24", start: "2026-10-12", end: "2026-10-23", status: "Active", velocity: 41 },
  { id: "Sprint 25", start: "2026-10-26", end: "2026-11-06", status: "Planned", velocity: 0 },
  { id: "Sprint 26", start: "2026-11-09", end: "2026-11-20", status: "Planned", velocity: 0 },
];

export interface PullRequest {
  id: string;
  title: string;
  repo: string;
  author: string;
  reviewers: string[];
  status: "Open" | "Approved" | "Changes requested" | "Merged";
  checks: "passing" | "failing" | "running";
  additions: number;
  deletions: number;
  updatedAt: string;
  taskKey: string;
}

export const pullRequests: PullRequest[] = [
  { id: "#482", title: "Stream telemetry over WebSocket with backoff", repo: "atlas-console-web", author: "LR-1020", reviewers: ["LR-1010"], status: "Open", checks: "passing", additions: 312, deletions: 64, updatedAt: "2026-10-23T09:40:00Z", taskKey: "ATLAS-101" },
  { id: "#479", title: "Role-based command permissions", repo: "atlas-telemetry-api", author: "LR-1011", reviewers: ["LR-1010", "LR-1031"], status: "Approved", checks: "passing", additions: 188, deletions: 21, updatedAt: "2026-10-23T08:05:00Z", taskKey: "ATLAS-102" },
  { id: "#233", title: "Invoice PDF download endpoint", repo: "orbit-portal", author: "LR-1021", reviewers: ["LR-1010"], status: "Changes requested", checks: "failing", additions: 140, deletions: 12, updatedAt: "2026-10-22T14:20:00Z", taskKey: "ORBIT-44" },
  { id: "#118", title: "Signed build artifacts with provenance", repo: "forge-pipelines", author: "LR-1024", reviewers: ["LR-1012"], status: "Open", checks: "running", additions: 421, deletions: 90, updatedAt: "2026-10-23T10:02:00Z", taskKey: "FORGE-12" },
  { id: "#97", title: "Dashboard CSV export with row limits", repo: "pulse-dashboards", author: "LR-1022", reviewers: ["LR-1011"], status: "Open", checks: "passing", additions: 96, deletions: 8, updatedAt: "2026-10-22T17:30:00Z", taskKey: "PULSE-72" },
  { id: "#96", title: "Backfill anomaly thresholds job", repo: "pulse-pipeline", author: "LR-1022", reviewers: ["LR-1011"], status: "Merged", checks: "passing", additions: 77, deletions: 15, updatedAt: "2026-10-20T11:00:00Z", taskKey: "PULSE-71" },
];
