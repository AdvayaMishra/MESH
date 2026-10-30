import {isLive,useLive} from "@/lib/connected/live-state";
/**
 * MESH API layer.
 *
 * Every function here returns a Promise and simulates network latency. Replace the bodies with real
 * `fetch` calls later; UI code only depends on these signatures. Results that are generated rather
 * than looked up are flagged `simulated: true` so the UI can label them honestly.
 */
import { getDataset } from "@/lib/api/use-dataset";
import { modelSpendQuestion } from "@/lib/what-if";
import { useTenant } from "@/stores/tenant-store";

export type { Dataset, OrgInfo } from "@/lib/api/dataset";
export { useDataset, getDataset } from "@/lib/api/use-dataset";

/** Active tenant dataset for async API calls (the mock adapter reads the active simulated org). */
const db = new Proxy({} as ReturnType<typeof getDataset>, { get: (_t, k) => (getDataset(useTenant.getState().orgId) as never)[k] });

const wait = <T,>(value: T, ms = 450): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms + Math.random() * 250));

export const api = {
  org: () => wait(db.org, 120),
  currentUser: () => wait(isLive()?db.employeeById(useLive.getState().profile?.user_id||""):db.employees[0], 80),

  // People
  employees: () => wait(db.employees),
  employee: (id: string) => wait(db.employeeById(id) ?? null),
  idSubmissions: () => wait(db.idSubmissions),
  leaveRequests: () => wait(db.leaveRequests),
  payroll: () => wait({ ...db.payrollSummary, simulated: true as const }),

  // Projects & tasks
  projects: () => wait(db.projects),
  tasks: () => wait(db.tasks),
  sprints: () => wait(db.sprints, 200),

  // Finance
  finance: () =>
    wait({
      kpis: db.orgKpis,
      monthlyCost: db.monthlyCost,
      providerSplit: db.providerSplit,
      utilization: db.utilization,
      departments: db.departmentStats,
    }),
  whatIf: (prompt: string) =>
    wait(
      {
        prompt,
        simulated: true as const,
        result: db.whatIfScenarios[prompt] ?? modelSpendQuestion(prompt, db.monthlyCost),
      },
      1100
    ),

  // Security
  repos: () => wait(db.repos),
  findings: () => wait(db.findings),
  incidents: () => wait(db.incidents),
  incident: (id: string) => wait(db.incidents.find((i) => i.id === id) ?? null),
  attackChain: () => wait(db.attackChain),
  riskComponents: () => wait(db.riskComponents),
  cloudResources: () => wait(db.cloudResources),

  // Shared
  notifications: () => wait(db.notifications, 200),
  auditLog: () => wait(db.auditLog),
  activity: () => wait(db.activity, 250),

  /** Simulated verification — never claims a real DNS or file lookup happened. */
  verifyWebsite: (method: "dns" | "file", code: string) => {
    if(isLive())return Promise.reject(new Error("Use Organization domain proof controls to verify both DNS and website ownership."));
    return wait({ method, code, simulated: true as const, verified: code.length > 0 }, 1600);
  },
};

export type Api = typeof api;
