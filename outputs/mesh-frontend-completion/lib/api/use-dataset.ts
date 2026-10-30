"use client";
import { isLive, useLive } from "@/lib/connected/live-state";
import { useSyncExternalStore } from "react";
import { readWorkspace, subscribeWorkspace, workspaceSnapshot, serverWorkspaceSnapshot } from "@/lib/api/workspace-source";
import { tenants, DEFAULT_ORG_ID } from "@/lib/api/mock";
import type { Dataset } from "@/lib/api/dataset";
import { useTenant } from "@/stores/tenant-store";
import { administration, useAdministration } from "@/stores/admin-store";
import { usePreferences, preferenceKey } from "@/stores/preferences-store";
import { useUI } from "@/stores/ui-store";

export function getDataset(orgId: string): Dataset {
  if(isLive()) return useLive.getState().data;
  const id = tenants[orgId] ? orgId : DEFAULT_ORG_ID;
  const base = tenants[id];
  const current = administration(id);
  const roleUsers = { ...base.roleUsers, ...usePreferences.getState().personas[id] };
  const live = readWorkspace(id);
  const projects = live?.projects ?? base.projects;
  const employees = current.employees.map((record) => {
    const employee = live?.projects ? { ...record, projects: projects.filter((p) => p.members.includes(record.id)).map((p) => p.id) } : record;
    const review = live?.idSubmissions?.find((item) => item.employee === employee.id);
    if (!review) return employee;
    const verification = review.status === "Approved" ? "Verified" as const : review.status === "Needs resubmission" ? "Needs resubmission" as const : "Pending review" as const;
    return { ...employee, verification };
  });
  const risk = base.riskTrend[base.riskTrend.length - 1]?.score;
  const orgKpis = { ...base.orgKpis, totalEmployees: employees.length, activeProjects: projects.filter((project) => project.status === "Active" || project.status === "At risk").length, securityPosture: risk === undefined ? base.orgKpis.securityPosture : 100 - risk };
  return { ...base, ...live, orgKpis, roleUsers, projectById: (projectId) => projects.find((p) => p.id === projectId), org: current.org, employees, employeeById: (employeeId) => employees.find((e) => e.id === employeeId), employeeName: (employeeId) => employees.find((e) => e.id === employeeId)?.name ?? "Unassigned" };
}

/** The active tenant's data plus the signed-in demo identity for the current role. */
export function useDataset() {
  const live=useLive();
  useSyncExternalStore(subscribeWorkspace, workspaceSnapshot, serverWorkspaceSnapshot);
  const orgId = useTenant((s) => s.orgId);
  const role = useUI((s) => s.role);
  useAdministration((s) => s.revision);
  usePreferences((s) => s.personas[orgId]);
  const photo = usePreferences((s) => s.photos[preferenceKey(orgId, role)]);
  const profile = usePreferences((s) => s.profiles[preferenceKey(orgId, role)]);
    const ds = getDataset(orgId);
    if(isLive())return {...ds,currentUser:{photo:undefined,id:live.profile?.user_id||"",name:live.profile?.name||live.profile?.owner_name||"Your account",email:live.profile?.email||"",role:live.profile?.role||""}};
    const me = ds.employeeById(ds.roleUsers[role]) ?? ds.employees[0];
    return { ...ds, currentUser: { photo, id: me.id, name: profile?.name ?? me.name, email: profile?.email ?? me.email, role: profile?.role ?? me.role } };
}
