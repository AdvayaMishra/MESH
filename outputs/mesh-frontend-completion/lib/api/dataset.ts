/**
 * Dataset contract: everything the UI can read about ONE organization (tenant).
 *
 * Today the mock adapter fills this in from `lib/api/mock/*`. A real HTTP adapter would populate the same shape from
 * backend endpoints (see BACKEND_INTEGRATION_GUIDE.md). UI code must only import from `@/lib/api`, never from
 * `@/lib/mock-data`. Entity shapes live in `@/lib/types`; analytics series reuse the mock shapes via `typeof` until the
 * backend contract is frozen.
 */
import type * as M from "@/lib/mock-data";
import type { Complaint, Employee, Project, Promotion, Role } from "@/lib/types";

export interface OrgInfo {
  name: string;
  domain: string;
  plan: string;
  region: string;
}

export interface RawDataset {
  id: string;
  /** Clearly-simulated tenant label shown in the switcher. */
  simulatedLabel: string;
  org: OrgInfo;
  /** Which employee each demo role signs in as. */
  roleUsers: Record<Role, string>;
  /** Seed decision history keyed by project id. */
  approvalHistory: Record<string, { id: string; at: string; by: string; action: string; note: string }[]>;
  monthlyCost: typeof M.monthlyCost;
  providerSplit: typeof M.providerSplit;
  utilization: typeof M.utilization;
  orgKpis: typeof M.orgKpis;
  kpiSparks: typeof M.kpiSparks;
  whatIfPrompts: typeof M.whatIfPrompts;
  whatIfScenarios: typeof M.whatIfScenarios;
  departmentStats: typeof M.departmentStats;
  projects: typeof M.projects;
  tasks: typeof M.tasks;
  sprints: ((typeof M.sprints)[number] & {name?:string})[];
  pullRequests: typeof M.pullRequests;
  repos: typeof M.repos;
  findings: typeof M.findings;
  vulnTrend: typeof M.vulnTrend;
  scanHistory: typeof M.scanHistory;
  dependencyRisk: typeof M.dependencyRisk;
  incidents: typeof M.incidents;
  attackChain: typeof M.attackChain;
  riskComponents: typeof M.riskComponents;
  riskTrend: typeof M.riskTrend;
  riskChangeLog: typeof M.riskChangeLog;
  loginActivity: typeof M.loginActivity;
  apiUsage: typeof M.apiUsage;
  deviceTimeline: typeof M.deviceTimeline;
  downloadAnomalies: typeof M.downloadAnomalies;
  employeeRiskDistribution: typeof M.employeeRiskDistribution;
  /** Tables read by unusual identities in the last 24h (VADER behavior page). */
  dbAccess: { table: string; rows: number; who: string; tone: "coral" | "amber" | "mint" }[];
  cloudResources: typeof M.cloudResources;
  cloudPosture: typeof M.cloudPosture;
  payrollSummary: typeof M.payrollSummary;
  idSubmissions: (Omit<(typeof M.idSubmissions)[number], "status"> & { status: "Pending review" | "Needs resubmission" | "Approved" })[];
  leaveRequests: typeof M.leaveRequests;
  employees: typeof M.employees;
  /** Seed HR cases. Read through the workspace store with viewer-scoped filtering, never rendered raw. */
  complaints: Complaint[];
  promotions: Promotion[];
  notifications: typeof M.notifications;
  activity: typeof M.activityFeed;
  auditLog: typeof M.auditLog;
}

export interface Dataset extends RawDataset {
  employeeById: (id: string) => Employee | undefined;
  employeeName: (id: string) => string;
  projectById: (id: string) => Project | undefined;
}

export function makeDataset(raw: RawDataset): Dataset {
  return {
    ...raw,
    employeeById: (id) => raw.employees.find((e) => e.id === id),
    employeeName: (id) => raw.employees.find((e) => e.id === id)?.name ?? "Unassigned",
    projectById: (id) => raw.projects.find((p) => p.id === id),
  };
}
