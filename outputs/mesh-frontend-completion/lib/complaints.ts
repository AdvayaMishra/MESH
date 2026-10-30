/**
 * Complaint privacy + workflow rules (pure functions, shared by UI and store).
 *
 * Visibility tiers:
 *  - "reviewer":    HR user who may read the full case (Standard/Confidential: any HR; Restricted: only the assignee).
 *  - "redacted":    HR user who may see that a Restricted case exists but not its contents.
 *  - "complainant": the person who filed it — sees only complainant-visible events.
 *  - "none":        everyone else (Owner, managers, the person complained about, other employees).
 * This is a UX/demo rule set. The backend must enforce the same rules server-side on every read.
 */
import type { Complaint, ComplaintCategory, ComplaintEvent, ComplaintStatus, Confidentiality, Role } from "@/lib/types";

export const COMPLAINT_CATEGORIES: ComplaintCategory[] = ["Harassment", "Discrimination", "Safety concern", "Policy violation", "Pay & benefits", "Management concern", "Workplace conduct", "Other"];
export const COMPLAINT_STATUSES: ComplaintStatus[] = ["Submitted", "Under review", "Investigating", "Resolved", "Closed", "Withdrawn"];
export const CONFIDENTIALITY_LEVELS: Confidentiality[] = ["Standard", "Confidential", "Restricted"];

export type ViewKind = "reviewer" | "redacted" | "complainant" | "none";
export interface Viewer { id: string; role: Role }

export function viewKind(c: Complaint, v: Viewer): ViewKind {
  if (v.role === "hr") {
    // Involved HR staff can't act as reviewers on their own complaint or one about them.
    const involved = c.submittedBy === v.id || c.concerning === v.id;
    if (involved) return c.submittedBy === v.id ? "complainant" : "none";
    if (c.confidentiality === "Restricted" && c.assignedTo !== v.id) return "redacted";
    return "reviewer";
  }
  return c.submittedBy === v.id ? "complainant" : "none";
}

export const visibleEvents = (c: Complaint, kind: ViewKind): ComplaintEvent[] =>
  kind === "reviewer" ? c.events : kind === "complainant" ? c.events.filter((e) => e.visibility === "complainant") : [];

/** Statuses a reviewer may move a case to from the current one. Resolution requires an outcome (see resolveComplaint). */
export const transitions: Record<ComplaintStatus, ComplaintStatus[]> = {
  Submitted: ["Under review", "Withdrawn"],
  "Under review": ["Investigating", "Resolved", "Withdrawn"],
  Investigating: ["Under review", "Resolved", "Withdrawn"],
  Resolved: ["Closed", "Investigating"], // Investigating = reopen
  Closed: [],
  Withdrawn: [],
};
export const isOpen = (c: Complaint) => c.status !== "Resolved" && c.status !== "Closed" && c.status !== "Withdrawn";

export function reporterLabel(c: Complaint, kind: ViewKind, name: (id: string) => string): string {
  if (kind === "complainant") return "You";
  return c.anonymous ? "Anonymous reporter" : name(c.submittedBy);
}

export interface ComplaintInput {
  title: string; category: ComplaintCategory; description: string; incidentDate: string;
  confidentiality: Confidentiality; anonymous: boolean; concerning?: string;
}
export function validateComplaint(i: Partial<ComplaintInput>, today: string): Record<string, string> {
  const e: Record<string, string> = {};
  if (!i.title || i.title.trim().length < 5) e.title = "Give the complaint a short title (at least 5 characters).";
  else if (i.title.length > 120) e.title = "Keep the title under 120 characters.";
  if (!i.category) e.category = "Choose a category.";
  if (!i.description || i.description.trim().length < 30) e.description = "Describe what happened in at least 30 characters.";
  else if (i.description.length > 4000) e.description = "Please keep the description under 4,000 characters.";
  if (!i.incidentDate) e.incidentDate = "Enter when it happened (approximate is fine).";
  else if (i.incidentDate > today) e.incidentDate = "The date can't be in the future.";
  if (!i.confidentiality || !["Standard", "Confidential"].includes(i.confidentiality)) e.confidentiality = "Choose Standard or Confidential. HR can escalate to Restricted.";
  return e;
}

/** Complaints this viewer may see at all, with the access tier they get. Everyone else's cases never reach the UI. */
export function visibleComplaints(all: Complaint[], v: Viewer): { c: Complaint; kind: Exclude<ViewKind, "none"> }[] {
  return all.flatMap((c) => { const kind = viewKind(c, v); return kind === "none" ? [] : [{ c, kind }]; });
}
export const RESOLUTION_OUTCOMES = ["Substantiated", "Partially substantiated", "Unsubstantiated", "Resolved informally", "No action required"] as const;
