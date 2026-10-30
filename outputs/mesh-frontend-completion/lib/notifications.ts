import { ALL_ROLES, canAccess } from "@/lib/permissions";
import { visibleAudit } from "@/lib/audit-visibility";
import type { AuditEntry, Notification, Role } from "@/lib/types";

/** Local demo business events create scoped inbox records; they never send an email or provider message. */
export function notificationFromAudit(entry: Omit<AuditEntry, "id" | "at" | "ip">, roleUsers: Record<Role, string>, complaintIds: string[]): Omit<Notification, "id" | "at" | "read"> | null {
  if (entry.module === "System" || entry.result !== "Simulated") return null;
  const safeEntry: AuditEntry = { ...entry, id: "visibility-check", at: "", ip: "" };
  const routes = { Owner: "/owner/projects", People: "/people", DevTrack: "/devtrack", VADER: "/vader/incidents" };
  const tones = { Owner: "violet", People: "mint", DevTrack: "sky", VADER: "coral" } as const;
  const href = routes[entry.module];
  const audience = [...new Set(ALL_ROLES.filter((role) => visibleAudit(safeEntry, role, complaintIds) && canAccess(role, href)).map((role) => roleUsers[role]))];
  if (!audience.length) return null;
  return { title: entry.action.slice(0, 140), body: `Demo update to ${entry.target.slice(0, 160)}`, module: entry.module, href, tone: tones[entry.module], audience };
}

/** Demo visibility only. Confidential cases require recipient-aware delivery on the server. */
export function visibleNotification(notification: Notification, role: Role, actorId?: string): boolean {
  if (notification.audience && (!actorId || !notification.audience.includes(actorId))) return false;
  const path = notification.href.split(/[?#]/)[0];
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) return false;
  // Generic notifications have no recipient/case access metadata; never publish case details here.
  if (/complaint/i.test(path + notification.title + notification.body)) return false;
  return canAccess(role, path);
}
