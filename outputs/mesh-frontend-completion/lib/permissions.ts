/**
 * Centralized route-permission configuration (single source of truth).
 *
 * IMPORTANT — this is a UX layer, NOT a security boundary. In demo mode the role comes from client state that anyone
 * can change. The real backend MUST independently enforce RBAC + tenant authorization on every request and never
 * trust a role sent by the browser.
 *
 * Matching: longest path-prefix wins. Unknown paths fail closed (Owner only).
 */
import type { Role } from "@/lib/types";

export const ALL_ROLES: Role[] = ["owner", "hr", "senior-dev", "junior-dev", "security-analyst"];
const DEV: Role[] = ["senior-dev", "junior-dev"];

export interface RouteRule {
  path: string;
  roles: Role[];
  /** Short human reason shown on the access-denied page. */
  note?: string;
}

export const routeRules: RouteRule[] = [
  { path: "/owner", roles: ["owner"], note: "Business finance and approvals are limited to the Owner." },
  { path: "/people", roles: ["owner", "hr"], note: "Employee records are limited to HR and the Owner." },
  { path: "/people/complaints", roles: ["hr"], note: "Complaints contain confidential case data and are limited to HR reviewers." },
  { path: "/people/promotions", roles: ["owner", "hr"], note: "Promotion proposals are limited to HR and the Owner." },
  { path: "/devtrack", roles: ["owner", ...DEV, "security-analyst"] },
  { path: "/vader", roles: ["owner", "security-analyst"], note: "Security operations data is limited to the Security team and the Owner." },
  { path: "/workspace", roles: ALL_ROLES },
  { path: "/workspace/complaints", roles: ALL_ROLES },
  { path: "/workspace/leave", roles: ALL_ROLES },
  { path: "/workspace/reports", roles: ["owner", "hr", "senior-dev", "security-analyst"], note: "Reports are not available to Junior Developers." },
  { path: "/workspace/audit", roles: ["owner", "security-analyst"], note: "The audit log is limited to the Owner and the Security team." },
  { path: "/workspace/organization", roles: ["owner", "hr"], note: "Organization settings are limited to the Owner and HR." },
];

const matches = (pathname: string, rule: string) => pathname === rule || pathname.startsWith(rule + "/");

export function ruleFor(pathname: string): RouteRule | undefined {
  const clean = pathname.split("?")[0].replace(/\/+$/, "") || "/";
  return routeRules.filter((r) => matches(clean, r.path)).sort((a, b) => b.path.length - a.path.length)[0];
}

export function canAccess(role: Role, pathname: string): boolean {
  const rule = ruleFor(pathname);
  return rule ? rule.roles.includes(role) : role === "owner";
}

export const roleHome: Record<Role, string> = {
  owner: "/owner",
  hr: "/people",
  "senior-dev": "/devtrack",
  "junior-dev": "/devtrack",
  "security-analyst": "/vader",
};
