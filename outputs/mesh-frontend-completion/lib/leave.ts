/** Basic leave rules (pure). No accrual, balances, payroll or tax logic by design. */
import type { LeaveRequest, LeaveType, Role } from "@/lib/types";

export const LEAVE_TYPES: LeaveType[] = ["Annual leave", "Casual leave", "Medical leave", "Unpaid leave"];
export const MAX_LEAVE_DAYS = 60;

/** Inclusive Monday–Friday count. */
export function weekdaysBetween(from: string, to: string): number {
  let n = 0;
  for (let t = Date.parse(from + "T00:00:00Z"); t <= Date.parse(to + "T00:00:00Z"); t += 86400000) { const d = new Date(t).getUTCDay(); if (d !== 0 && d !== 6) n++; }
  return n;
}
export interface LeaveInput { type: string; from: string; to: string; reason: string }
export function validateLeave(i: Partial<LeaveInput>, ctx: { today: string; employeeId: string; existing: LeaveRequest[] }): Record<string, string> {
  const e: Record<string, string> = {};
  if (!i.type || !LEAVE_TYPES.includes(i.type as LeaveType)) e.type = "Choose a leave type.";
  if (!i.from) e.from = "Choose a start date.";
  else if (i.from < ctx.today) e.from = "Start date can't be in the past.";
  if (!i.to) e.to = "Choose an end date.";
  else if (i.from && i.to < i.from) e.to = "End date can't be before the start date.";
  if (!e.from && !e.to && i.from && i.to) {
    if (weekdaysBetween(i.from, i.to) === 0) e.to = "The selected dates contain no working days.";
    else if (weekdaysBetween(i.from, i.to) > MAX_LEAVE_DAYS) e.to = `Requests are limited to ${MAX_LEAVE_DAYS} working days.`;
    else if (ctx.existing.some((l) => l.employee === ctx.employeeId && (l.status === "Pending" || l.status === "Approved") && i.from! <= l.to && i.to! >= l.from)) e.from = "These dates overlap another pending or approved request of yours.";
  }
  if (i.reason && i.reason.length > 500) e.reason = "Keep the note under 500 characters.";
  if (i.type === "Medical leave" && (!i.reason || i.reason.trim().length < 5)) e.reason = "Add a brief note for medical leave (details stay private to HR).";
  return e;
}
/** HR/Owner may review; never your own request. */
export const canReviewLeave = (role: Role, actorId: string, l: LeaveRequest) => (role === "hr" || role === "owner") && l.employee !== actorId && l.status === "Pending";
