import type { AuditEntry, Role } from "@/lib/types";
import { canAccess } from "@/lib/permissions";
/** Confidential case history belongs to case-scoped views, never the shared audit/export/feed. */
export function visibleAudit(entry: AuditEntry, role: Role, complaintIds: readonly string[]): boolean {
  if (/complaint/i.test(entry.action) || complaintIds.some((id) => entry.target === id || entry.target.startsWith(id + " "))) return false;
  return entry.module === "System" || canAccess(role, `/${entry.module.toLowerCase()}`);
}
