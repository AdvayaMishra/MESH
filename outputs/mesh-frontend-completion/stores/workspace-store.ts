import { isLive } from "@/lib/connected/live-state";
import { registerWorkspaceSource } from "@/lib/api/workspace-source";
import { notificationFromAudit, visibleNotification } from "@/lib/notifications";
import { create } from "zustand";
import { getDataset } from "@/lib/api/use-dataset";
import { DEFAULT_ORG_ID } from "@/lib/api/mock";
import { useUI } from "@/stores/ui-store";
import type { Dataset } from "@/lib/api/dataset";
import { TRUST_MAX_DELTA, scoreFromEvents } from "@/lib/trust";
import { viewKind, validateComplaint, transitions, type ComplaintInput } from "@/lib/complaints";
import { canDecide, canPropose, validatePromotion, initialApprovals, gradeOf, type PromotionInput } from "@/lib/promotions";
import { validateLeave, canReviewLeave, weekdaysBetween, type LeaveInput } from "@/lib/leave";
import type { Complaint, ComplaintOutcome, ComplaintStatus, LeaveRequest, Promotion, AuditEntry, Finding, FindingStatus, Incident, Notification, Project, ProjectStatus, Task, TaskStatus, TrustEvent } from "@/lib/types";

type IdSubmission = Omit<Dataset["idSubmissions"][number], "status"> & { status: "Pending review" | "Needs resubmission" | "Approved" };
type Leave = LeaveRequest;
export type Result<T = object> = ({ ok: true } & T) | { ok: false; error: string };

export interface IncidentResponseEvent {
  id: string;
  actionId: string;
  actionLabel: string;
  at: string;
  actor: string;
  note: string;
  undone: boolean;
  undoneAt?: string;
}

export interface DecisionLog {
  id: string;
  at: string;
  by: string;
  action: string;
  note: string;
}

/** Mutable, per-organization demo state. Each simulated tenant keeps its own slice; nothing is shared between them. */
interface Slice {
  cloudRemediations: Record<string, { at: string; actor: string }>;
  payrollReviews: Record<string, "Reviewed" | "Flagged for Finance">;
  payrollRun: { status: "Prepared" | "Approved"; preparedBy: string; at: string; approvedBy?: string } | null;
  scanHistory: Dataset["scanHistory"];
  projects: Project[];
  tasks: Task[];
  sprints: Dataset["sprints"];
  pullRequests: Dataset["pullRequests"];
  repos: Dataset["repos"];
  prReviews: Record<string, { id: string; actor: string; at: string; decision: "Approved" | "Changes requested"; note: string }[]>;
  findings: Finding[];
  incidents: Incident[];
  incidentNotes: Record<string, { id: string; at: string; actor: string; text: string }[]>;
  incidentResponses: Record<string, IncidentResponseEvent[]>;
  notifications: Notification[];
  idSubmissions: IdSubmission[];
  leave: Leave[];
  audit: AuditEntry[];
  complaints: Complaint[];
  promotions: Promotion[];
  approvalHistory: Record<string, DecisionLog[]>;
  /** Reviewed Trust events recorded this session, per employee id (newest first). */
  trustEvents: Record<string, TrustEvent[]>;
}

interface WorkspaceState extends Slice {
  preparePayroll: () => Result;
  approvePayroll: () => Result;
  setProjectMember: (projectId: string, employeeId: string, included: boolean) => Result;
  reviewPayroll: (id: string, status: "Reviewed" | "Flagged for Finance") => Result;
  remediateCloud: (id: string, undo?: boolean) => Result;
  orgId: string;
  snapshots: Record<string, Slice>;
  /** Save the current org's slice and load (or seed) another's. */
  switchOrg: (orgId: string) => void;
  completeDemoScan: (repo: string, runId: string) => Result;
  endorseProject: (id: string) => Result;
  setProjectStatus: (id: string, status: ProjectStatus, note: string) => Result;
  addProject: (p: Project) => Result;
  setTaskStatus: (id: string, status: TaskStatus) => Result;
  assignTask: (id: string, assignee: string) => Result;
  addTask: (t: Task) => Result;
  deleteTask: (id: string) => Result;
  createSprint: (id: string, start: string, end: string) => Result;
  setSprintStatus: (id: string, status: "Active" | "Completed") => Result;
  mergePullRequest: (id: string, reason: string) => Result;
  reviewPullRequest: (id: string, decision: "Approved" | "Changes requested", note: string) => Result;
  setRepositoryAuthorization: (name: string, authorized: boolean) => Result;
  updateTask: (id: string, patch: Partial<Pick<Task, "title" | "description" | "priority" | "points" | "labels" | "due" | "sprint">>) => Result;
  addComment: (taskId: string, author: string, text: string) => Result;
  setFindingStatus: (id: string, status: FindingStatus) => Result;
  assignFinding: (id: string, assignee: string) => Result;
  addIncidentNote: (id: string, text: string) => Result;
  setIncidentStatus: (id: string, status: Incident["status"], riskAfter?: number) => Result;
  approveIncidentResponse: (incidentId: string, actionId: string, actionLabel: string, note: string) => Result;
  undoIncidentResponse: (incidentId: string, eventId: string) => Result;
  addNotification: (n: Omit<Notification, "id" | "at" | "read">) => void;
  markNotification: (id: string, read?: boolean) => void;
  markAllNotifications: () => void;
  submitDemoId: (employeeId: string) => Result;
  decideId: (id: string, status: IdSubmission["status"], note: string) => Result;
  decideLeave: (id: string, status: "Approved" | "Rejected", note?: string) => Result;
  submitLeave: (input: Partial<LeaveInput>) => Result<{ id: string }>;
  cancelLeave: (id: string) => Result;
  // HR: complaints (every action re-checks the viewer's access tier; the backend must do the same)
  submitComplaint: (input: Partial<ComplaintInput>) => Result<{ id: string }>;
  setComplaintStatus: (id: string, to: ComplaintStatus, note?: string) => Result;
  resolveComplaint: (id: string, outcome: ComplaintOutcome, summary: string) => Result;
  withdrawComplaint: (id: string) => Result;
  assignComplaintToMe: (id: string) => Result;
  escalateComplaint: (id: string) => Result;
  addComplaintMessage: (id: string, text: string, internal?: boolean) => Result;
  // HR: promotions
  createPromotion: (input: Partial<PromotionInput>) => Result<{ id: string }>;
  decidePromotion: (id: string, decision: "Approved" | "Rejected", note: string) => Result;
  withdrawPromotion: (id: string) => Result;
  log: (e: Omit<AuditEntry, "id" | "at" | "ip">) => void;
  /** Records a human-reviewed Trust event. Validates input; never called automatically. */
  recordTrustEvent: (employeeId: string, delta: number, reason: string, source: TrustEvent["source"]) => { ok: true; score: number } | { ok: false; error: string };
}

const validDay = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
const projectProgress = (projects: Project[], tasks: Task[]) => projects.map((project) => {
  const assigned = tasks.filter((task) => task.projectId === project.id);
  return { ...project, progress: assigned.length ? Math.round(100 * assigned.filter((task) => task.status === "Done").length / assigned.length) : 0 };
});
const now = () => new Date().toISOString();
const today = () => now().slice(0, 10);
const fail = (error: string): { ok: false; error: string } => ({ ok: false, error });
type SetFn = (fn: (s: WorkspaceState) => Partial<WorkspaceState>) => void;
type GetFn = () => WorkspaceState;
const ctx = (get: GetFn) => { const d = getDataset(get().orgId); const id = d.roleUsers[useUI.getState().role]; return { d, id, name: d.employeeName(id), role: useUI.getState().role }; };
const evt = (actor: string, kind: Complaint["events"][number]["kind"], text: string, visibility: "complainant" | "hr" = "complainant") => ({ id: crypto.randomUUID(), at: now(), actor, kind, text, visibility });
const nextId = (prefix: string, list: { id: string }[]) => `${prefix}-${Math.max(100, ...list.map((x) => parseInt(x.id.replace(/\D/g, ""), 10) || 0)) + 1}`;

const seed = (orgId: string): Slice => {
  const d = getDataset(orgId);
  return {
    cloudRemediations: {}, payrollReviews: {}, payrollRun: null, scanHistory: d.scanHistory,
    projects: d.projects,
    tasks: d.tasks,
    sprints: d.sprints,
    pullRequests: d.pullRequests,
    repos: d.repos,
    prReviews: {},
    findings: d.findings,
    incidents: d.incidents,
    incidentNotes: {}, incidentResponses: {},
    notifications: d.notifications,
    idSubmissions: d.idSubmissions as IdSubmission[],
    leave: d.leaveRequests as LeaveRequest[],
    audit: d.auditLog,
    complaints: d.complaints,
    promotions: d.promotions,
    approvalHistory: d.approvalHistory,
    trustEvents: {},
  };
};
const sliceOf = (s: WorkspaceState): Slice => ({
  payrollRun: s.payrollRun, scanHistory: s.scanHistory, cloudRemediations: s.cloudRemediations, payrollReviews: s.payrollReviews,
  projects: s.projects, tasks: s.tasks, sprints: s.sprints, pullRequests: s.pullRequests, repos: s.repos, prReviews: s.prReviews, findings: s.findings, incidents: s.incidents, incidentNotes: s.incidentNotes, incidentResponses: s.incidentResponses, notifications: s.notifications,
  idSubmissions: s.idSubmissions, leave: s.leave, audit: s.audit, complaints: s.complaints, promotions: s.promotions, approvalHistory: s.approvalHistory, trustEvents: s.trustEvents,
});

/** Name of the person the demo is currently "signed in" as, in the active organization. */
export const currentActor = (orgId?: string) => {
  const d = getDataset(orgId ?? useWorkspace.getState().orgId);
  return d.employeeName(d.roleUsers[useUI.getState().role]);
};


function hrActions(set: SetFn, get: GetFn): Pick<WorkspaceState, "decideLeave" | "submitLeave" | "cancelLeave" | "submitComplaint" | "setComplaintStatus" | "resolveComplaint" | "withdrawComplaint" | "assignComplaintToMe" | "escalateComplaint" | "addComplaintMessage" | "createPromotion" | "decidePromotion" | "withdrawPromotion"> {
  /** Applies a change to one complaint only if the actor is a reviewer (or, when allowed, the complainant). */
  const mutateComplaint = (id: string, who: "reviewer" | "complainant", fn: (c: Complaint, actorId: string) => Complaint | string, audit: string): Result => {
    const { id: actorId, role, name } = ctx(get);
    const c = get().complaints.find((x) => x.id === id);
    const kind = c ? viewKind(c, { id: actorId, role }) : "none";
    if (!c || kind !== who) return fail("You don't have access to this case.");
    const next = fn(c, actorId);
    if (typeof next === "string") return fail(next);
    set((s) => ({ complaints: s.complaints.map((x) => (x.id === id ? { ...next, updatedAt: now() } : x)) }));
    get().log({ actor: name, action: `${audit} (simulated)`, target: id, module: "People", result: "Simulated" });
    return { ok: true };
  };
  return {
    submitLeave: (input) => {
      const { id: actorId, name } = ctx(get);
      const errs = validateLeave(input, { today: today(), employeeId: actorId, existing: get().leave });
      const first = Object.values(errs)[0];
      if (first) return fail(first);
      const l: LeaveRequest = { id: nextId("L", get().leave), employee: actorId, type: input.type!, from: input.from!, to: input.to!, days: weekdaysBetween(input.from!, input.to!), status: "Pending", reason: input.reason?.trim() || undefined, submittedAt: now() };
      set((s) => ({ leave: [l, ...s.leave] }));
      get().log({ actor: name, action: "Submitted leave request (simulated)", target: l.id, module: "People", result: "Simulated" });
      return { ok: true, id: l.id };
    },
    cancelLeave: (id) => {
      const { id: actorId, name } = ctx(get);
      const l = get().leave.find((x) => x.id === id);
      if (!l || l.employee !== actorId) return fail("You can only cancel your own requests.");
      if (l.status !== "Pending") return fail("Only pending requests can be cancelled.");
      set((s) => ({ leave: s.leave.map((x) => (x.id === id ? { ...x, status: "Cancelled" } : x)) }));
      get().log({ actor: name, action: "Cancelled leave request (simulated)", target: id, module: "People", result: "Simulated" });
      return { ok: true };
    },
    decideLeave: (id, status, note = "") => {
      const { id: actorId, role, name } = ctx(get);
      const l = get().leave.find((x) => x.id === id);
      if (!l) return fail("Request not found.");
      if (!canReviewLeave(role, actorId, l)) return fail(l.employee === actorId ? "You can't review your own request." : l.status !== "Pending" ? "This request is already decided." : "Only HR or the Owner can review leave.");
      if (status === "Rejected" && note.trim().length < 5) return fail("Add a short reason (5+ characters) when declining.");
      set((s) => ({ leave: s.leave.map((x) => (x.id === id ? { ...x, status, reviewedBy: actorId, reviewNote: note.trim() || undefined } : x)) }));
      get().log({ actor: name, action: `Leave ${status.toLowerCase()} (simulated)`, target: id, module: "People", result: "Simulated" });
      return { ok: true };
    },

    submitComplaint: (input) => {
      const { d, id: actorId, name } = ctx(get);
      const errs = validateComplaint(input, today());
      if (Object.keys(errs).length) return fail(Object.values(errs)[0]);
      if (input.concerning && (input.concerning === actorId || !d.employeeById(input.concerning))) return fail("Choose a different colleague, or leave 'concerning' blank.");
      const t = now();
      const c: Complaint = {
        id: nextId(d.id === "lumen" ? "C" : "NC", get().complaints), title: input.title!.trim(), category: input.category!, description: input.description!.trim(),
        confidentiality: input.confidentiality!, status: "Submitted", priority: ["Harassment", "Discrimination", "Safety concern"].includes(input.category!) ? "High" : "Medium",
        submittedBy: actorId, anonymous: !!input.anonymous, concerning: input.concerning || undefined, incidentDate: input.incidentDate!, createdAt: t, updatedAt: t,
        events: [evt(actorId, "Submitted", "Complaint submitted.")],
      };
      set((s) => ({ complaints: [c, ...s.complaints] }));
      get().log({ actor: name, action: "Submitted complaint (simulated)", target: c.id, module: "People", result: "Simulated" });
      return { ok: true, id: c.id };
    },
    setComplaintStatus: (id, to, note) => mutateComplaint(id, "reviewer", (c, a) => {
      if (to === "Withdrawn") return "Only the person who filed a complaint can withdraw it.";
      if (to === "Resolved") return "Use 'Resolve' so an outcome and summary are recorded.";
      if (!transitions[c.status].includes(to)) return `A case can't move from ${c.status} to ${to}.`;
      const reopen = c.status === "Resolved" && to === "Investigating";
      const text = `${reopen ? "Reopened" : "Moved"} to ${to}.${note?.trim() ? " " + note.trim() : ""}`;
      return { ...c, status: to, resolution: reopen ? undefined : c.resolution, assignedTo: c.assignedTo ?? a, events: [...c.events, evt(a, reopen ? "Reopened" : "Status change", text)] };
    }, `Complaint moved to ${to}`),
    resolveComplaint: (id, outcome, summary) => mutateComplaint(id, "reviewer", (c, a) => {
      if (!transitions[c.status].includes("Resolved")) return `A case can't be resolved from ${c.status}.`;
      if (summary.trim().length < 20) return "Write a resolution summary of at least 20 characters.";
      return { ...c, status: "Resolved", assignedTo: c.assignedTo ?? a, resolution: { outcome, summary: summary.trim(), resolvedAt: now(), resolvedBy: a }, events: [...c.events, evt(a, "Resolution", `Resolved. Outcome: ${outcome}.`)] };
    }, "Complaint resolved"),
    withdrawComplaint: (id) => mutateComplaint(id, "complainant", (c, a) => (!transitions[c.status].includes("Withdrawn") ? `A ${c.status.toLowerCase()} case can't be withdrawn.` : { ...c, status: "Withdrawn", events: [...c.events, evt(a, "Withdrawn", "Withdrawn by the person who filed it.")] }), "Complaint withdrawn"),
    assignComplaintToMe: (id) => mutateComplaint(id, "reviewer", (c, a) => ({ ...c, assignedTo: a, events: [...c.events, evt(a, "Assigned", "Case assigned to reviewer.", "hr")] }), "Complaint assigned"),
    escalateComplaint: (id) => mutateComplaint(id, "reviewer", (c, a) => (c.confidentiality === "Restricted" ? "Already restricted." : { ...c, confidentiality: "Restricted", assignedTo: a, events: [...c.events, evt(a, "Escalated", "Escalated to Restricted. Only the assigned reviewer can open this case.", "hr")] }), "Complaint escalated to Restricted"),
    addComplaintMessage: (id, text, internal = false) => {
      const { id: actorId, role } = ctx(get);
      const c = get().complaints.find((x) => x.id === id);
      const kind = c ? viewKind(c, { id: actorId, role }) : "none";
      const who = kind === "reviewer" ? "reviewer" : "complainant";
      if (text.trim().length < 2) return fail("Write a message first.");
      if (internal && kind !== "reviewer") return fail("Only reviewers can add internal notes.");
      return mutateComplaint(id, who, (cc, a) => ({ ...cc, events: [...cc.events, evt(a, internal ? "Internal note" : "Message", text.trim(), internal ? "hr" : "complainant")] }), internal ? "Internal note added" : "Complaint message added");
    },

    createPromotion: (input) => {
      const { d, id: actorId, role, name } = ctx(get);
      if (!canPropose(role)) return fail("Only HR or the Owner can propose promotions.");
      const emp = input.employeeId ? d.employeeById(input.employeeId) : undefined;
      const errs = validatePromotion(input, { employee: emp, proposerId: actorId, existing: get().promotions, today: today() });
      if (Object.keys(errs).length) return fail(Object.values(errs)[0]);
      const t = now();
      const { approvals, status } = initialApprovals(role, actorId, t);
      const p: Promotion = { id: nextId(d.id === "lumen" ? "P" : "NP", get().promotions), employeeId: emp!.id, currentRole: emp!.role, proposedRole: input.proposedRole!.trim(), currentGrade: gradeOf(emp!), proposedGrade: input.proposedGrade!, effectiveDate: input.effectiveDate!, justification: input.justification!.trim(), proposedBy: actorId, createdAt: t, status, approvals, events: [{ id: crypto.randomUUID(), at: t, actor: actorId, text: `Proposal created and sent for ${status === "Pending HR review" ? "HR review" : "Owner approval"}.` }] };
      set((s) => ({ promotions: [p, ...s.promotions] }));
      get().log({ actor: name, action: "Created promotion proposal (simulated)", target: `${p.id} ${emp!.name}`, module: "People", result: "Simulated" });
      return { ok: true, id: p.id };
    },
    decidePromotion: (id, decision, note) => {
      const { d, id: actorId, role, name } = ctx(get);
      const p = get().promotions.find((x) => x.id === id);
      if (!p) return fail("Proposal not found.");
      const can = canDecide(p, role, actorId);
      if (!can.ok) return fail(can.reason);
      if (decision === "Rejected" && note.trim().length < 10) return fail("Add a reason (10+ characters) when rejecting.");
      const step = p.status === "Pending HR review" ? "HR review" : "Owner approval";
      const approvals = p.approvals.map((a) => (a.step === step ? { ...a, state: decision, by: actorId, at: now(), note: note.trim() || undefined } : a));
      const status: Promotion["status"] = decision === "Rejected" ? "Rejected" : approvals.every((a) => a.state === "Approved") ? "Approved" : p.status;
      const e = { id: crypto.randomUUID(), at: now(), actor: actorId, text: `${step} ${decision.toLowerCase()}.${note.trim() ? " " + note.trim() : ""}` };
      set((s) => ({ promotions: s.promotions.map((x) => (x.id === id ? { ...x, approvals, status, events: [...x.events, e] } : x)) }));
      get().log({ actor: name, action: `Promotion ${decision.toLowerCase()} (simulated; no salary, role or access change)`, target: `${id} ${d.employeeName(p.employeeId)}`, module: "People", result: "Simulated" });
      return { ok: true };
    },
    withdrawPromotion: (id) => {
      const { id: actorId, name } = ctx(get);
      const p = get().promotions.find((x) => x.id === id);
      if (!p || p.proposedBy !== actorId) return fail("Only the proposer can withdraw a proposal.");
      if (p.status !== "Pending HR review" && p.status !== "Pending Owner approval") return fail("Only proposals in review can be withdrawn.");
      set((s) => ({ promotions: s.promotions.map((x) => (x.id === id ? { ...x, status: "Withdrawn", events: [...x.events, { id: crypto.randomUUID(), at: now(), actor: actorId, text: "Withdrawn by proposer." }] } : x)) }));
      get().log({ actor: name, action: "Withdrew promotion proposal (simulated)", target: id, module: "People", result: "Simulated" });
      return { ok: true };
    },
  };
}

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  orgId: DEFAULT_ORG_ID,
  snapshots: {},
  ...seed(DEFAULT_ORG_ID),
  switchOrg: (orgId) =>
    set((s) => {
      if (s.orgId === orgId) return s;
      const snapshots = { ...s.snapshots, [s.orgId]: sliceOf(s) };
      return { ...(snapshots[orgId] ?? seed(orgId)), orgId, snapshots };
    }),
  preparePayroll: () => {
    const { role, id, name, d } = ctx(get);
    if (!["owner", "hr"].includes(role)) return fail("Payroll preparation requires HR or owner access.");
    if (get().payrollRun) return fail("This demonstration payroll run has already been prepared.");
    if (d.payrollSummary.discrepancies.some((v) => get().payrollReviews[v.id] !== "Reviewed")) return fail("Review every payroll discrepancy before preparing the run.");
    set({ payrollRun: { status: "Prepared", preparedBy: id, at: now() } });
    get().log({ actor: name, action: "Prepared payroll for independent approval (demo only)", target: d.payrollSummary.month, module: "People", result: "Simulated" });
    return { ok: true };
  },
  approvePayroll: () => {
    const { role, id, name, d } = ctx(get);
    if (!["owner", "hr"].includes(role)) return fail("Payroll approval requires HR or owner access.");
    const run = get().payrollRun;
    if (!run || run.status !== "Prepared") return fail("Prepare a payroll run before approval.");
    if (run.preparedBy === id) return fail("A different reviewer must approve this payroll run.");
    set({ payrollRun: { ...run, status: "Approved", approvedBy: id } });
    get().log({ actor: name, action: "Approved payroll (demo; no money transferred)", target: d.payrollSummary.month, module: "People", result: "Simulated" });
    return { ok: true };
  },
  setProjectMember: (projectId, employeeId, included) => {
    const { role, name, d } = ctx(get);
    if (!["owner", "senior-dev"].includes(role)) return fail("Only the owner and senior developers can allocate project members.");
    const project = get().projects.find((p) => p.id === projectId);
    const employee = d.employeeById(employeeId);
    if (!project || !employee) return fail("Project and employee must belong to this organization.");
    if (project.lead === employeeId && !included) return fail("The project lead must remain a member.");
    if (employee.status === "Offboarding" || employee.status === "Onboarding") return fail("Complete onboarding or choose an active employee.");
    if (project.members.includes(employeeId) === included) return fail("This project allocation is already recorded.");
    set((s) => ({ projects: s.projects.map((p) => p.id === projectId ? { ...p, members: included ? [...p.members, employeeId] : p.members.filter((id) => id !== employeeId) } : p) }));
    get().log({ actor: name, action: `Project member ${included ? "allocated" : "removed"} (simulated)`, target: `${projectId} ${employeeId}`, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  reviewPayroll: (id, status) => {
    const { role, d, name } = ctx(get);
    if (!["owner", "hr"].includes(role)) return fail("Payroll review requires HR or owner access.");
    if (!d.payrollSummary.discrepancies.some((v) => v.id === id)) return fail("Discrepancy not found in this organization.");
    if (!["Reviewed", "Flagged for Finance"].includes(status)) return fail("Invalid payroll review state.");
    if (get().payrollReviews[id] === status) return fail("This review is already recorded.");
    set((s) => ({ payrollReviews: { ...s.payrollReviews, [id]: status } }));
    get().log({ actor: name, action: `Payroll ${status.toLowerCase()} (simulated)`, target: id, module: "People", result: "Simulated" });
    return { ok: true };
  },
  remediateCloud: (id, undo = false) => {
    const { role, d, name } = ctx(get);
    if (!["owner", "security-analyst"].includes(role)) return fail("Cloud review requires owner or security access.");
    if (!d.cloudResources.some((v) => v.id === id)) return fail("Resource not found in this organization.");
    if (Boolean(get().cloudRemediations[id]) === !undo) return fail("This remediation state is already recorded.");
    set((s) => { const next = { ...s.cloudRemediations }; if (undo) delete next[id]; else next[id] = { at: now(), actor: name }; return { cloudRemediations: next }; });
    get().log({ actor: name, action: `Cloud remediation ${undo ? "reopened" : "marked done"} (simulated)`, target: id, module: "VADER", result: "Simulated" });
    return { ok: true };
  },
  completeDemoScan: (repo, runId) => {
    const { role, name } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev", "security-analyst"].includes(role)) return fail("Your role cannot simulate repository scans.");
    const target = get().repos.find((r) => r.name === repo);
    if (!target?.authorized) return fail("The owner must authorize this repository.");
    if (!runId || get().scanHistory.some((s) => s.id === runId)) return fail("This simulated run was already recorded.");
    const findings = get().findings.filter((f) => f.repo === repo && f.status !== "Fixed").length;
    const record = { id: runId, repo, at: now(), duration: "Demo animation", findings, scanners: ["Semgrep", "Bandit", "Gitleaks", "OSV"], status: "Completed (simulated)" };
    set((s) => ({ scanHistory: [record, ...s.scanHistory] }));
    get().log({ actor: name, action: "Repository scan simulation completed; no tools executed", target: repo, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  endorseProject: (id) => {
    const { role, name } = ctx(get);
    if (role !== "senior-dev") return fail("Only senior developers can endorse proposals.");
    const project = get().projects.find((p) => p.id === id);
    if (!project || project.status !== "Awaiting approval") return fail("Select a pending proposal in this organization.");
    if ((get().approvalHistory[id] ?? []).some((e) => e.by === name && e.action === "Endorsed")) return fail("You already endorsed this proposal.");
    set((s) => ({ approvalHistory: { ...s.approvalHistory, [id]: [{ id: crypto.randomUUID(), at: now(), by: name, action: "Endorsed", note: "Senior developer recommendation for owner review (simulated)." }, ...(s.approvalHistory[id] ?? [])] } }));
    get().log({ actor: name, action: "Proposal endorsed (simulated)", target: id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  setProjectStatus: (id, status, note) => {
    const { role, name } = ctx(get);
    if (role !== "owner") return fail("Only the owner can decide project proposals.");
    const project = get().projects.find((p) => p.id === id);
    if (!project) return fail("Project not found in this organization.");
    if (project.status !== "Awaiting approval") return fail("This project is not awaiting approval.");
    if (status !== "Active" && status !== "Rejected") return fail("Choose approve or reject.");
    if (status === "Rejected" && note.trim().length < 3) return fail("Enter a reason for rejection.");
    const decisionNote = note.trim() || "Approved without comment";
    set((s) => ({
      projects: s.projects.map((p) => p.id === id ? { ...p, status } : p),
      approvalHistory: { ...s.approvalHistory, [id]: [{ id: crypto.randomUUID(), at: now(), by: name, action: status === "Active" ? "Approved" : "Rejected", note: decisionNote }, ...(s.approvalHistory[id] ?? [])] },
    }));
    get().log({ actor: name, action: `Project ${status === "Active" ? "approved" : "rejected"} (simulated)`, target: id, module: "Owner", result: "Simulated" });
    return { ok: true };
  },
  addProject: (p) => {
    const { role, id, name } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev"].includes(role)) return fail("Only owners and developers can propose projects.");
    if (p.proposedBy !== id || p.lead !== id || p.status !== "Awaiting approval") return fail("A proposal must be submitted under your own demo identity.");
    if (p.name.trim().length < 3 || p.description.trim().length < 20 || !Number.isFinite(p.budget) || p.budget < 1000 || !validDay(p.dueDate)) return fail("Enter a valid name, description, budget and due date.");
    if (get().projects.some((x) => x.id === p.id || x.key === p.key)) return fail("Project identifier already exists.");
    set((s) => ({ projects: [p, ...s.projects] }));
    get().log({ actor: name, action: "Submitted project proposal (simulated)", target: p.id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  setTaskStatus: (id, status) => {
    const { role, name } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev"].includes(role)) return fail("Only developers and the owner can update tasks.");
    if (!get().tasks.some((t) => t.id === id)) return fail("Task not found in this organization.");
    if (!["Backlog", "To do", "In progress", "In review", "Done"].includes(status)) return fail("Invalid task status.");
    set((s) => { const tasks = s.tasks.map((t) => t.id === id ? { ...t, status } : t); return { tasks, projects: projectProgress(s.projects, tasks) }; });
    get().log({ actor: name, action: `Task moved to ${status} (simulated)`, target: id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  assignTask: (id, assignee) => {
    const { role, name, d } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev"].includes(role)) return fail("Only developers and the owner can assign tasks.");
    if (!get().tasks.some((t) => t.id === id)) return fail("Task not found in this organization.");
    const employee = d.employeeById(assignee);
    if (!employee || !["senior-dev", "junior-dev"].includes(employee.appRole) || employee.status === "Onboarding") return fail("Choose an active developer from this organization.");
    set((s) => ({ tasks: s.tasks.map((t) => t.id === id ? { ...t, assignee } : t) }));
    get().log({ actor: name, action: "Task reassigned (simulated)", target: id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  addTask: (t) => {
    const { role, name, d } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev"].includes(role)) return fail("You cannot create tasks.");
    if (!get().projects.some((p) => p.id === t.projectId && ["Active", "At risk"].includes(p.status))) return fail("Choose an active project.");
    const assignee = d.employeeById(t.assignee);
    if (!assignee || !["senior-dev", "junior-dev"].includes(assignee.appRole)) return fail("Choose a developer in this organization.");
    if (t.title.trim().length < 3 || !Number.isInteger(t.points) || t.points < 0 || t.points > 100 || !validDay(t.due)) return fail("Enter a title, due date and valid points.");
    if (!["Backlog", "To do", "In progress", "In review", "Done"].includes(t.status) || !["Critical", "High", "Medium", "Low"].includes(t.priority) || (t.sprint !== "Backlog" && !get().sprints.some((s) => s.id === t.sprint))) return fail("Choose a valid task status, priority and sprint.");
    if (get().tasks.some((existing) => existing.id === t.id || existing.key === t.key)) return fail("A task with this identifier already exists.");
    set((s) => { const tasks = [t, ...s.tasks]; return { tasks, projects: projectProgress(s.projects, tasks) }; });
    get().log({ actor: name, action: "Created task (simulated)", target: t.key, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  deleteTask: (id) => {
    const { role, name } = ctx(get);
    if (role !== "owner" && role !== "senior-dev") return fail("Only owners and senior developers can delete tasks.");
    const task = get().tasks.find((t) => t.id === id);
    if (!task) return fail("Task not found in this organization.");
    if (get().pullRequests.some((pr) => pr.taskKey === task.key)) return fail("This task is linked to a pull request and cannot be deleted in the demo.");
    set((s) => { const tasks = s.tasks.filter((t) => t.id !== id); return { tasks, projects: projectProgress(s.projects, tasks) }; });
    get().log({ actor: name, action: "Deleted task (simulated)", target: task.key, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  createSprint: (id, start, end) => {
    const { role, name } = ctx(get);
    if (role !== "owner" && role !== "senior-dev") return fail("Only the owner or a senior developer can plan sprints.");
    const title = id.trim();
    if (title.length < 3 || title.length > 80 || title.toLowerCase() === "backlog") return fail("Enter a sprint name between 3 and 80 characters.");
    if (get().sprints.some((s) => s.id.toLowerCase() === title.toLowerCase())) return fail("A sprint with this name already exists.");
    const valid = (date: string) => /^\d{4}-\d{2}-\d{2}$/.test(date) && !Number.isNaN(Date.parse(date + "T00:00:00Z")) && new Date(date + "T00:00:00Z").toISOString().slice(0, 10) === date;
    if (!valid(start) || !valid(end) || end < start) return fail("Choose valid start and end dates in order.");
    set((s) => ({ sprints: [...s.sprints, { id: title, start, end, status: "Planned", velocity: 0 }] }));
    get().log({ actor: name, action: "Created sprint (simulated)", target: title, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  setSprintStatus: (id, status) => {
    const { role, name } = ctx(get);
    if (role !== "owner" && role !== "senior-dev") return fail("Only the owner or a senior developer can manage sprints.");
    const sprint = get().sprints.find((s) => s.id === id);
    if (!sprint) return fail("Sprint not found in this organization.");
    if ((status === "Active" && sprint.status !== "Planned") || (status === "Completed" && sprint.status !== "Active")) return fail("Only planned sprints can start and only active sprints can complete.");
    if (status === "Active" && get().sprints.some((s) => s.status === "Active")) return fail("Complete the active sprint first.");
    const velocity = status === "Completed" ? get().tasks.filter((t) => t.sprint === id && t.status === "Done").reduce((n, t) => n + t.points, 0) : sprint.velocity;
    set((s) => ({ sprints: s.sprints.map((sp) => sp.id === id ? { ...sp, status, velocity } : sp) }));
    get().log({ actor: name, action: `Sprint ${status.toLowerCase()} (simulated)`, target: id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  setRepositoryAuthorization: (repoName, authorized) => {
    const { role, name } = ctx(get);
    if (role !== "owner") return fail("Only the owner can change repository authorization.");
    const repo = get().repos.find((r) => r.name === repoName);
    if (!repo) return fail("Repository not found in this organization.");
    if (repo.authorized === authorized) return fail("Authorization already has that setting.");
    set((s) => ({ repos: s.repos.map((r) => r.name === repoName ? { ...r, authorized } : r) }));
    get().log({ actor: name, action: `Repository authorization ${authorized ? "granted" : "revoked"} (simulated)`, target: repoName, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  reviewPullRequest: (id, decision, note) => {
    const { role, id: actorId, name } = ctx(get);
    if (role !== "owner" && role !== "senior-dev") return fail("Only owners or senior developers can review pull requests.");
    const pr = get().pullRequests.find((p) => p.id === id);
    if (!pr) return fail("Pull request not found in this organization.");
    if (pr.author === actorId) return fail("You cannot review your own pull request.");
    if (role === "senior-dev" && !pr.reviewers.includes(actorId)) return fail("Only assigned reviewers can review this pull request.");
    if (pr.status === "Merged") return fail("Merged pull requests cannot be reviewed.");
    if (decision !== "Approved" && decision !== "Changes requested") return fail("Invalid review decision.");
    if (pr.status === decision) return fail("This decision is already recorded.");
    if (note.trim().length < 10) return fail("Enter a review note of at least 10 characters.");
    const review = { id: crypto.randomUUID(), actor: name, at: now(), decision, note: note.trim() };
    set((s) => ({ pullRequests: s.pullRequests.map((p) => p.id === id ? { ...p, status: decision, updatedAt: review.at } : p), prReviews: { ...s.prReviews, [id]: [review, ...(s.prReviews[id] ?? [])] } }));
    get().log({ actor: name, action: `Pull request ${decision.toLowerCase()} (simulated)`, target: `${pr.repo} ${id}`, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  mergePullRequest: (id, reason) => {
    const { role, name } = ctx(get);
    if (role !== "senior-dev" && role !== "owner") return fail("Only senior developers or owners can merge pull requests.");
    const pr = get().pullRequests.find((p) => p.id === id);
    if (!pr) return fail("Pull request not found in this organization.");
    if (pr.status === "Merged") return fail("This pull request has already been merged.");
    if (pr.status !== "Approved") return fail("A pull request must be approved before merging.");
    if (pr.checks !== "passing") return fail("All automated checks must pass before merging.");
    if (reason.trim().length < 10) return fail("Provide a merge justification of at least 10 characters.");
    set((s) => ({ pullRequests: s.pullRequests.map((p) => p.id === id ? { ...p, status: "Merged" as const, updatedAt: now() } : p) }));
    get().log({ actor: name, action: `Merged pull request (simulated): ${reason.trim()}`, target: `${pr.repo} ${pr.id}`, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  updateTask: (id, patch) => {
    const { role, name } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev"].includes(role)) return fail("Only developers and the owner can edit tasks.");
    const task = get().tasks.find((t) => t.id === id);
    if (!task) return fail("Task not found in this organization.");
    const next = { ...task, ...patch };
    if (next.title.trim().length < 3 || next.title.length > 200 || !Number.isInteger(next.points) || next.points < 0 || next.points > 100) return fail("Enter a title of 3Ã¢â‚¬“200 characters and points between 0 and 100.");
    if (!["Critical", "High", "Medium", "Low"].includes(next.priority)) return fail("Invalid priority.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(next.due) || Number.isNaN(Date.parse(next.due)) || new Date(next.due).toISOString().slice(0,10) !== next.due) return fail("Enter a valid due date.");
    if (next.sprint !== "Backlog" && !get().sprints.some((s) => s.id === next.sprint)) return fail("Sprint not found in this organization.");
    if (next.labels.length > 20 || next.labels.some((v) => !v.trim() || v.length > 40)) return fail("Use up to 20 labels of 1Ã¢â‚¬“40 characters.");
    set((s) => ({ tasks: s.tasks.map((t) => t.id === id ? { ...next, title: next.title.trim(), labels: [...new Set(next.labels.map((v) => v.trim()))] } : t) }));
    get().log({ actor: name, action: "Task details updated (simulated)", target: id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  addComment: (taskId, author, text) => {
    const { role, id, name } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev"].includes(role) || author !== id) return fail("Comments must use your own developer or owner identity.");
    if (!get().tasks.some((t) => t.id === taskId)) return fail("Task not found in this organization.");
    if (!text.trim() || text.length > 5000) return fail("Enter a comment of 1Ã¢â‚¬“5000 characters.");
    set((s) => ({ tasks: s.tasks.map((t) => t.id === taskId ? { ...t, comments: [...t.comments, { id: crypto.randomUUID(), author, at: now(), text: text.trim() }] } : t) }));
    get().log({ actor: name, action: "Task comment added (simulated)", target: taskId, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  setFindingStatus: (id, status) => {
    const { role, id: actorId, name } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev", "security-analyst"].includes(role)) return fail("You cannot update security findings.");
    if (role === "junior-dev" && (status === "Accepted risk" || !get().findings.some((f) => f.id === id && f.assignee === actorId))) return fail("Junior developers can remediate their assigned findings; risk acceptance requires a reviewer.");
    if (!get().findings.some((f) => f.id === id)) return fail("Finding not found in this organization.");
    if (!["Open", "In progress", "Fixed", "Accepted risk"].includes(status)) return fail("Invalid finding status.");
    set((s) => ({ findings: s.findings.map((f) => f.id === id ? { ...f, status } : f) }));
    get().log({ actor: name, action: `Finding marked ${status} (simulated)`, target: id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  assignFinding: (id, assignee) => {
    const { role, name, d } = ctx(get);
    if (!["owner", "senior-dev", "junior-dev", "security-analyst"].includes(role)) return fail("You cannot assign security findings.");
    if (!get().findings.some((f) => f.id === id)) return fail("Finding not found in this organization.");
    const employee = d.employeeById(assignee);
    if (!employee || !["senior-dev", "junior-dev", "security-analyst"].includes(employee.appRole)) return fail("Select an eligible person in this organization.");
    set((s) => ({ findings: s.findings.map((f) => f.id === id ? { ...f, assignee } : f) }));
    get().log({ actor: name, action: `Assigned finding to ${employee.name} (simulated)`, target: id, module: "DevTrack", result: "Simulated" });
    return { ok: true };
  },
  addIncidentNote: (id, text) => {
    const { role, name } = ctx(get);
    if (!["owner", "security-analyst"].includes(role)) return fail("Only security analysts and the owner can add investigation notes.");
    if (!get().incidents.some((i) => i.id === id)) return fail("Incident not found in this organization.");
    if (text.trim().length < 10 || text.length > 5000) return fail("Enter a note of 10–5000 characters.");
    const note = { id: crypto.randomUUID(), at: now(), actor: name, text: text.trim() };
    set((s) => ({ incidentNotes: { ...s.incidentNotes, [id]: [note, ...(s.incidentNotes[id] ?? [])] } }));
    get().log({ actor: name, action: "Investigation note added (simulated)", target: id, module: "VADER", result: "Simulated" });
    return { ok: true };
  },
  setIncidentStatus: (id, status, riskAfter) => {
    const { role, name } = ctx(get);
    if (role !== "owner" && role !== "security-analyst") return fail("Only the owner or security analyst can update incidents.");
    const incident = get().incidents.find((i) => i.id === id);
    if (!incident) return fail("Incident not found in this organization.");
    if (!["Open", "Investigating", "Contained", "Resolved"].includes(status)) return fail("Invalid incident status.");
    if (incident.status === "Resolved") return fail("Resolved incidents cannot be changed in this demo.");
    if (status === incident.status) return fail("Incident already has this status.");
    if (riskAfter !== undefined && (!Number.isFinite(riskAfter) || riskAfter < 0 || riskAfter > 100)) return fail("Invalid risk score.");
    set((s) => ({ incidents: s.incidents.map((i) => i.id === id ? { ...i, status, riskAfter: riskAfter ?? i.riskAfter } : i) }));
    get().log({ actor: name, action: `Incident marked ${status} (simulated)`, target: id, module: "VADER", result: "Simulated" });
    return { ok: true };
  },
  approveIncidentResponse: (incidentId, actionId, actionLabel, note) => {
    if (!["owner", "security-analyst"].includes(ctx(get).role)) return fail("Only the owner or security analyst can approve responses.");
    const incident = get().incidents.find((i) => i.id === incidentId);
    if (!incident) return fail("Incident not found.");
    if (incident.status === "Resolved") return fail("Resolved incidents cannot receive new responses.");
    const responseLabels: Record<string, string> = { revoke: "Revoke active sessions", rotate: "Rotate access key", block: "Block external destination" };
    if (responseLabels[actionId] !== actionLabel) return fail("Unknown response action.");
    if (!note.trim() || note.trim().length < 10) return fail("Enter a reason of at least 10 characters.");
    const existing = get().incidentResponses[incidentId] ?? [];
    if (existing.some((e) => e.actionId === actionId && !e.undone)) return fail("This response is already active.");
    const actor = currentActor();
    const event: IncidentResponseEvent = { id: crypto.randomUUID(), actionId, actionLabel, at: now(), actor, note: note.trim(), undone: false };
    set((s) => ({ incidentResponses: { ...s.incidentResponses, [incidentId]: [event, ...(s.incidentResponses[incidentId] ?? [])] } }));
    get().log({ actor, action: `Approved simulated response: ${actionLabel}`, target: incidentId, module: "VADER", result: "Simulated" });
    return { ok: true };
  },
  undoIncidentResponse: (incidentId, eventId) => {
    if (!["owner", "security-analyst"].includes(ctx(get).role)) return fail("Only the owner or security analyst can reverse responses.");
    const event = (get().incidentResponses[incidentId] ?? []).find((e) => e.id === eventId && !e.undone);
    if (!event) return fail("Active response not found.");
    set((s) => ({ incidentResponses: { ...s.incidentResponses, [incidentId]: (s.incidentResponses[incidentId] ?? []).map((e) => e.id === eventId ? { ...e, undone: true, undoneAt: now() } : e) } }));
    get().log({ actor: currentActor(), action: `Reversed simulated response: ${event.actionLabel}`, target: incidentId, module: "VADER", result: "Simulated" });
    return { ok: true };
  },
  addNotification: (n) => set((s) => ({ notifications: [{ ...n, id: `N-${crypto.randomUUID().slice(0, 6)}`, at: now(), read: false }, ...s.notifications] })),
  markNotification: (id, read = true) => set((s) => ({ notifications: s.notifications.map((n) => (n.id === id && visibleNotification(n, useUI.getState().role, ctx(get).id) ? { ...n, read } : n)) })),
  markAllNotifications: () => set((s) => ({ notifications: s.notifications.map((n) => visibleNotification(n, useUI.getState().role, ctx(get).id) ? { ...n, read: true } : n) })),
  submitDemoId: (employeeId) => {
    const d = getDataset(get().orgId);
    const employee = d.employeeById(employeeId);
    if (!employee || employee.status !== "Onboarding") return fail("Choose an onboarding employee in this demo organization.");
    const existing = get().idSubmissions.find((v) => v.employee === employeeId);
    if (existing?.status === "Approved") return fail("This identity has already been reviewed.");
    const fields = { name: employee.name, dob: "Sample only", idNumber: "Masked demo value", expiry: "Sample only" };
    const item: IdSubmission = { id: existing?.id ?? `ID-${crypto.randomUUID()}`, employee: employee.id, docType: "Demo identity preview", submittedAt: now(), status: "Pending review", submitted: fields, ocr: { ...fields }, confidence: { name: 0, dob: 0, idNumber: 0, expiry: 0 }, history: [{ at: now(), by: employee.name, action: "Submitted demo preview", note: "No document was uploaded or OCR performed. Fields are synthetic." }, ...(existing?.history ?? [])] };
    set((s) => ({ idSubmissions: [item, ...s.idSubmissions.filter((v) => v.id !== item.id)] }));
    get().log({ actor: employee.name, action: "Demo identity submitted for human review", target: item.id, module: "People", result: "Simulated" });
    return { ok: true };
  },
  decideId: (id, status, note) => {
    const { role, id: actorId, name } = ctx(get);
    if (role !== "owner" && role !== "hr") return fail("Only HR or the owner can review identity submissions.");
    const submission = get().idSubmissions.find((v) => v.id === id);
    if (!submission) return fail("Submission not found in this organization.");
    if (submission.employee === actorId) return fail("You cannot review your own identity submission.");
    if (submission.status !== "Pending review") return fail("Only pending submissions can be reviewed.");
    if (status !== "Approved" && status !== "Needs resubmission") return fail("Invalid review decision.");
    if (status === "Needs resubmission" && note.trim().length < 3) return fail("Enter a resubmission note.");
    const action = status === "Approved" ? "Approved" : "Requested resubmission";
    const review = { at: now(), by: name, action, note: note.trim() || "No note" };
    set((s) => ({ idSubmissions: s.idSubmissions.map((v) => v.id === id ? { ...v, status, history: [review, ...v.history] } : v) }));
    get().log({ actor: name, action: `${action} ID verification (simulated)`, target: id, module: "People", result: "Simulated" });
    return { ok: true };
  },
  ...hrActions(set, get),
  log: (e) => set((s) => {
    const at = now();
    const notice = notificationFromAudit(e, getDataset(s.orgId).roleUsers, s.complaints.map((c) => c.id));
    return { audit: [{ id: `AU-${9100 + s.audit.length}`, at, ip: "Demo", ...e }, ...s.audit], notifications: notice ? [{ ...notice, id: `N-${crypto.randomUUID()}`, at, read: false }, ...s.notifications] : s.notifications };
  }),
  recordTrustEvent: (employeeId, delta, reason, source) => {
    if (!["owner", "hr"].includes(useUI.getState().role)) return fail("Only HR or the owner can record a Trust event.");
    const d = getDataset(get().orgId);
    const emp = d.employeeById(employeeId);
    const actorId = d.roleUsers[useUI.getState().role];
    if (!emp || emp.trustScore === null) return { ok: false, error: "This person's role isn't eligible for Trust Stars." };
    if (employeeId === actorId) return { ok: false, error: "You can't record a Trust event about yourself." };
    if (!Number.isInteger(delta) || delta === 0 || Math.abs(delta) > TRUST_MAX_DELTA) return { ok: false, error: `Change must be a whole number between -${TRUST_MAX_DELTA} and ${TRUST_MAX_DELTA}, and not zero.` };
    if (reason.trim().length < 10) return { ok: false, error: "Describe the reviewed event in at least 10 characters." };
    const by = d.employeeName(actorId);
    const event: TrustEvent = { id: crypto.randomUUID(), date: now().slice(0, 10), delta, reason: reason.trim(), source, reviewedBy: by };
    const next = [event, ...(get().trustEvents[employeeId] ?? [])];
    set((s) => ({ trustEvents: { ...s.trustEvents, [employeeId]: next } }));
    get().log({ actor: by, action: `Recorded reviewed Trust event ${delta > 0 ? "+" : ""}${delta} (simulated)`, target: `${emp.id} ${emp.name}`, module: "People", result: "Simulated" });
    return { ok: true, score: scoreFromEvents([...next, ...emp.trustEvents]) };
  },
}));

registerWorkspaceSource({
  subscribe: (notify) => useWorkspace.subscribe(notify),
  snapshot: () => useWorkspace.getState(),
  read: (org) => {
    const state = useWorkspace.getState();
    const source = state.orgId === org ? state : state.snapshots[org];
    if (!source) return null;
    return { scanHistory: source.scanHistory, projects: source.projects, tasks: source.tasks, sprints: source.sprints, pullRequests: source.pullRequests, repos: source.repos, findings: source.findings, incidents: source.incidents, idSubmissions: source.idSubmissions as Dataset["idSubmissions"], leaveRequests: source.leave, complaints: source.complaints, promotions: source.promotions, notifications: source.notifications, auditLog: source.audit, approvalHistory: source.approvalHistory };
  },
});

// Connected mode cannot mutate demo stores or report demo persistence as success.
for(const [name, action] of Object.entries(useWorkspace.getState())) {
 if(typeof action!=="function")continue;
 const original=action as (...args:unknown[])=>unknown;
 useWorkspace.setState({[name]:(...args:unknown[])=>{
  if(isLive())return name==="log"?undefined:{ok:false,error:"Use the connected server controls for this action. This demo action does not save backend records."};
  return original(...args);
 }});
}
