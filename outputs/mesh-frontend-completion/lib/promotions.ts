/** Promotion proposal rules (pure). Approval never changes salary, role records or access permissions in this system. */
import type { Employee, Promotion, PromotionApproval, Role } from "@/lib/types";

/** Grade ladders keyed by prefix. Tenants use different band schemes (Lumen: E/S/G, Northwind: N/N-S/N-G). */
export const GRADE_LADDERS: Record<string, number> = { E: 7, S: 5, G: 5, N: 7, "N-S": 5, "N-G": 5 };
export const gradeOf = (e: Employee) => e.salaryBand.replace(/^Band\s+/i, "");
const parseGrade = (g: string) => { const m = /^([A-Z]+(?:-[A-Z]+)?)(\d+)$/.exec(g); return m ? { prefix: m[1], n: Number(m[2]) } : null; };
export const ladderFor = (grade: string) => { const p = parseGrade(grade); const max = p && GRADE_LADDERS[p.prefix]; return p && max ? Array.from({ length: max }, (_, i) => `${p.prefix}${i + 1}`) : []; };
export const higherGrades = (grade: string) => { const p = parseGrade(grade); return p ? ladderFor(grade).filter((g) => (parseGrade(g)?.n ?? 0) > p.n) : []; };
export const isOpenPromotion = (p: Promotion) => p.status === "Pending HR review" || p.status === "Pending Owner approval" || p.status === "Draft";

export interface PromotionInput { employeeId: string; proposedRole: string; proposedGrade: string; effectiveDate: string; justification: string }

export function validatePromotion(i: Partial<PromotionInput>, ctx: { employee?: Employee; proposerId: string; existing: Promotion[]; today: string }): Record<string, string> {
  const e: Record<string, string> = {};
  const emp = ctx.employee;
  if (!emp) { e.employeeId = "Select an employee."; return e; }
  if (emp.id === ctx.proposerId) e.employeeId = "You can't propose your own promotion.";
  else if (emp.status !== "Active") e.employeeId = `${emp.name} is ${emp.status.toLowerCase()}; only active employees can be proposed.`;
  else if (ctx.existing.some((p) => p.employeeId === emp.id && (p.status === "Pending HR review" || p.status === "Pending Owner approval"))) e.employeeId = `${emp.name} already has a proposal in review.`;
  const cur = gradeOf(emp);
  if (!i.proposedRole || i.proposedRole.trim().length < 3) e.proposedRole = "Enter the proposed role title.";
  if (!i.proposedGrade) e.proposedGrade = "Choose a proposed grade.";
  else if (!higherGrades(cur).includes(i.proposedGrade)) e.proposedGrade = `Proposed grade must be higher than ${cur} on the same ladder.`;
  if (!i.effectiveDate) e.effectiveDate = "Choose an effective date.";
  else if (i.effectiveDate < ctx.today) e.effectiveDate = "The effective date can't be in the past.";
  else if (i.effectiveDate > addMonths(ctx.today, 12)) e.effectiveDate = "Effective date must be within 12 months.";
  if (!i.justification || i.justification.trim().length < 40) e.justification = "Explain the case in at least 40 characters (impact, scope, evidence).";
  return e;
}

export const addMonths = (iso: string, n: number) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCMonth(d.getUTCMonth() + n); return d.toISOString().slice(0, 10); };

/** Proposer ≠ final approver: whichever of HR/Owner proposes has their own step recorded as sponsored. */
export function initialApprovals(proposerRole: Role, proposerId: string, at: string): { approvals: PromotionApproval[]; status: Promotion["status"] } {
  if (proposerRole === "owner")
    return { status: "Pending HR review", approvals: [{ step: "HR review", state: "Pending" }, { step: "Owner approval", state: "Approved", by: proposerId, at, note: "Sponsored by proposer" }] };
  return { status: "Pending Owner approval", approvals: [{ step: "HR review", state: "Approved", by: proposerId, at, note: "Sponsored by proposer" }, { step: "Owner approval", state: "Pending" }] };
}
/** Which role may act on the current pending step. */
export const actingRoleFor = (p: Promotion): Role | null => (p.status === "Pending HR review" ? "hr" : p.status === "Pending Owner approval" ? "owner" : null);

/** Who may create proposals / act on a pending step (UX layer; the backend must enforce the same). */
export const canPropose = (role: Role) => role === "hr" || role === "owner";
export function canDecide(p: Promotion, role: Role, actorId: string): { ok: true } | { ok: false; reason: string } {
  const need = actingRoleFor(p);
  if (!need) return { ok: false, reason: "This proposal is no longer pending." };
  if (role !== need) return { ok: false, reason: need === "hr" ? "Waiting for HR review." : "Waiting for Owner approval." };
  if (actorId === p.employeeId) return { ok: false, reason: "You can't decide your own promotion." };
  if (actorId === p.proposedBy) return { ok: false, reason: "The proposer can't approve their own proposal." };
  return { ok: true };
}
