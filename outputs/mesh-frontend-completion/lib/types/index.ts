import type { Severity } from "@/lib/design-tokens";

export type Role = "owner" | "hr" | "senior-dev" | "junior-dev" | "security-analyst";

export type Department =
  | "Engineering"
  | "Product"
  | "Design"
  | "Security"
  | "Finance"
  | "People Ops"
  | "Sales"
  | "Infrastructure";

export type EmploymentStatus = "Active" | "On leave" | "Onboarding" | "Offboarding" | "Probation";
export type VerificationStatus = "Verified" | "Pending review" | "Needs resubmission" | "Not submitted";

export interface TrustEvent {
  id: string;
  date: string;
  delta: number;
  reason: string;
  source: string;
  reviewedBy?: string;
}

export interface Employee {
  id: string; // e.g. LR-1042
  name: string;
  email: string;
  role: string;
  appRole: Role;
  department: Department;
  status: EmploymentStatus;
  verification: VerificationStatus;
  joinDate: string;
  manager?: string;
  location: string;
  projects: string[]; // project ids
  /** 0–50 points (1 star per 10), decision-support only. `null` = role not eligible for Trust Stars. */
  trustScore: number | null;
  /** Newest first. Deltas are in points. Score = 20 + sum(deltas), bounded 0–50. */
  trustEvents: TrustEvent[];
  salaryBand: string;
  riskScore: number; // 0-100 VADER behavioural signal
}

export type ProjectStatus = "Planning" | "Awaiting approval" | "Active" | "At risk" | "Completed" | "Rejected";
export type Priority = "Critical" | "High" | "Medium" | "Low";

export interface Project {
  id: string;
  key: string;
  name: string;
  description: string;
  status: ProjectStatus;
  priority: Priority;
  progress: number;
  lead: string; // employee id
  members: string[];
  budget: number;
  spent: number;
  department: Department;
  dueDate: string;
  proposedBy?: string;
  proposedAt?: string;
  cloud: "AWS" | "Azure" | "GCP";
  repos: string[];
}

export type TaskStatus = "Backlog" | "To do" | "In progress" | "In review" | "Done";

export interface Task {
  metadataKnown?: boolean;
  id: string;
  key: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  assignee: string;
  projectId: string;
  points: number;
  labels: string[];
  sprint: string;
  due: string;
  comments: { id: string; author: string; at: string; text: string }[];
}

export type Scanner = "Semgrep" | "Bandit" | "Gitleaks" | "OSV";
export type FindingStatus = "Open" | "In progress" | "Fixed" | "Accepted risk";

export interface Finding {
  id: string;
  title: string;
  severity: Severity;
  scanner: Scanner;
  repo: string;
  file: string;
  line: number;
  evidence: string; // sanitized
  remediation: string;
  status: FindingStatus;
  assignee: string;
  cwe?: string;
  detectedAt: string;
}

export interface Repo {
  name: string;
  language: string;
  health: number;
  coverage: number;
  openFindings: number;
  lastScan: string;
  authorized: boolean;
  projectId: string;
}

export interface Incident {
  id: string;
  title: string;
  severity: Severity;
  status: "Open" | "Investigating" | "Contained" | "Resolved";
  detectedAt: string;
  summary: string;
  assets: string[];
  analyst: string;
  riskBefore: number;
  riskAfter: number;
  chainId?: string;
}

export interface ChainNode {
  id: string;
  label: string;
  detail: string;
  at: string;
  severity: Severity;
  risk: number;
  evidence: string[];
  source: string;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  at: string;
  module: "Owner" | "People" | "DevTrack" | "VADER" | "System";
  read: boolean;
  href: string;
  /** Employee ids who may see this notification. Omitted = visible to everyone in the org. */
  audience?: string[];
  tone: "violet" | "mint" | "amber" | "coral" | "sky";
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
  target: string;
  module: "Owner" | "People" | "DevTrack" | "VADER" | "System";
  result: "Success" | "Denied" | "Simulated";
  ip: string;
}

export interface CloudResource {
  id: string;
  name: string;
  provider: "AWS" | "Azure" | "GCP";
  type: string;
  region: string;
  risk: Severity;
  issue: string;
  owner: string;
}

/* ───────────── HR: complaints ───────────── */
export type ComplaintCategory =
  | "Harassment" | "Discrimination" | "Safety concern" | "Policy violation" | "Pay & benefits" | "Management concern" | "Workplace conduct" | "Other";
export type ComplaintStatus = "Submitted" | "Under review" | "Investigating" | "Resolved" | "Closed" | "Withdrawn";
/** Standard: any HR reviewer. Confidential: HR reviewers only. Restricted: assigned reviewer only (need-to-know). */
export type Confidentiality = "Standard" | "Confidential" | "Restricted";
export type ComplaintOutcome = "Substantiated" | "Partially substantiated" | "Unsubstantiated" | "Resolved informally" | "No action required";

export interface ComplaintEvent {
  id: string;
  at: string;
  actor: string; // employee id, or "system"
  kind: "Submitted" | "Assigned" | "Status change" | "Message" | "Internal note" | "Resolution" | "Reopened" | "Withdrawn" | "Escalated";
  text: string;
  /** "complainant" events are visible to the person who filed it; "hr" events are reviewer-only. */
  visibility: "complainant" | "hr";
}

export interface Complaint {
  id: string;
  title: string;
  category: ComplaintCategory;
  description: string;
  confidentiality: Confidentiality;
  status: ComplaintStatus;
  priority: "Low" | "Medium" | "High";
  submittedBy: string; // employee id
  /** Hide the reporter's identity from reviewers (simulated; real anonymity depends on backend design). */
  anonymous: boolean;
  /** Employee the complaint concerns, if any. Never shown to that employee. */
  concerning?: string;
  incidentDate: string;
  createdAt: string;
  updatedAt: string;
  assignedTo?: string; // HR employee id
  events: ComplaintEvent[];
  resolution?: { outcome: ComplaintOutcome; summary: string; resolvedAt: string; resolvedBy: string; followUpDate?: string };
}

/* ───────────── HR: promotions ───────────── */
export type PromotionStatus = "Draft" | "Pending HR review" | "Pending Owner approval" | "Approved" | "Rejected" | "Withdrawn";
export interface PromotionApproval {
  step: "HR review" | "Owner approval";
  state: "Pending" | "Approved" | "Rejected" | "Not required";
  by?: string; // employee id
  at?: string;
  note?: string;
}
export interface PromotionEvent { id: string; at: string; actor: string; text: string }
export interface Promotion {
  id: string;
  employeeId: string;
  currentRole: string;
  proposedRole: string;
  currentGrade: string;
  proposedGrade: string;
  effectiveDate: string;
  justification: string;
  proposedBy: string;
  createdAt: string;
  status: PromotionStatus;
  approvals: PromotionApproval[];
  events: PromotionEvent[];
}

/* ───────────── HR: leave ───────────── */
export type LeaveType = "Annual leave" | "Casual leave" | "Medical leave" | "Unpaid leave";
export type LeaveStatus = "Pending" | "Approved" | "Rejected" | "Cancelled";
export interface LeaveRequest {
  id: string;
  employee: string; // employee id
  type: string;
  from: string;
  to: string;
  days: number; // weekdays, inclusive
  status: string;
  reason?: string;
  submittedAt?: string;
  reviewedBy?: string;
  reviewNote?: string;
}
