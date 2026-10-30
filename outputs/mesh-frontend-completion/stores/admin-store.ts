import { isLive } from "@/lib/connected/live-state";
import { create } from "zustand";
import { tenants } from "@/lib/api/mock";
import { useTenant } from "@/stores/tenant-store";
import { useUI } from "@/stores/ui-store";
import type { AuditEntry, Department, Employee, Role } from "@/lib/types";
import type { OrgInfo } from "@/lib/api/dataset";
export const departments: Department[] = ["Engineering", "Product", "Design", "Security", "Finance", "People Ops", "Sales", "Infrastructure"];
export interface LifecyclePlan { id: string; employeeId: string; mode: "onboarding" | "offboarding"; status: "Pending" | "Approved" | "Executed" | "Reversed"; proposedBy: string; approvedBy?: string; before: Employee["status"]; at: string }
export interface Administration { plans: LifecyclePlan[]; org: OrgInfo; employees: Employee[]; budgets: Partial<Record<Department, number>>; audit: AuditEntry[] }
type Result = { ok: true } | { ok: false; error: string };
const fail = (error: string): Result => ({ ok: false, error });
interface State {
  revision: number;
  organizations: Record<string, Administration>;
  proposeLifecycle: (employeeId: string, mode: LifecyclePlan["mode"]) => Result;
  transitionLifecycle: (id: string, action: "approve" | "execute" | "reverse") => Result;
  saveOrganization: (name: string, domain: string) => Result;
  setBudget: (department: Department, amount: number) => Result;
  addEmployee: (input: { name: string; email: string; title: string; department: Department; appRole: Role }) => Result;
  updateEmployee: (id: string, patch: Pick<Employee, "department" | "appRole" | "status">) => Result;
}
export function administration(org: string): Administration {
  const existing = useAdministration.getState().organizations[org];
  if (existing) return existing;
  const d = tenants[org];
  if (!d) throw new Error("Unknown demonstration organization");
  return { plans: [], org: d.org, employees: d.employees, budgets: {}, audit: [] };
}
export const useAdministration = create<State>((set) => {
  const context = () => { const org = useTenant.getState().orgId; const role = useUI.getState().role; const state = administration(org); const actorId = tenants[org].roleUsers[role]; return { org, role, state, actorId }; };
  const save = (org: string, state: Administration, action: string, target: string, actor: string) => set((s) => ({ revision: s.revision + 1, organizations: { ...s.organizations, [org]: { ...state, audit: [{ id: crypto.randomUUID(), at: new Date().toISOString(), actor, action, target, module: /employee|lifecycle/i.test(action) ? "People" : "Owner", result: "Simulated", ip: "Demo" }, ...state.audit] } } }));
  return {
    revision: 0, organizations: {},
    proposeLifecycle: (employeeId, mode) => {
      const c = context();
      if (!["owner", "hr"].includes(c.role)) return fail("Only HR or the owner can propose lifecycle plans.");
      const employee = c.state.employees.find((e) => e.id === employeeId);
      if (!employee || employee.appRole === "owner" || employeeId === c.actorId) return fail("Choose another non-owner employee in this organization.");
      if (!["onboarding", "offboarding"].includes(mode)) return fail("Invalid lifecycle mode.");
      if (mode === "onboarding" && employee.status !== "Onboarding") return fail("Only onboarding employees can complete onboarding.");
      if (c.state.plans.some((p) => p.employeeId === employeeId && p.status !== "Reversed")) return fail("A plan for this employee is already recorded; reverse it before proposing another.");
      const plan: LifecyclePlan = { id: crypto.randomUUID(), employeeId, mode, status: "Pending", proposedBy: c.actorId, before: employee.status, at: new Date().toISOString() };
      save(c.org, { ...c.state, plans: [plan, ...c.state.plans] }, "Lifecycle plan proposed (simulated)", plan.id, c.actorId);
      return { ok: true };
    },
    transitionLifecycle: (id, action) => {
      const c = context();
      if (!["owner", "hr"].includes(c.role)) return fail("Only HR or the owner can review lifecycle plans.");
      const plan = c.state.plans.find((p) => p.id === id);
      if (!plan) return fail("Plan not found in this organization.");
      const employee = c.state.employees.find((e) => e.id === plan.employeeId);
      if (!employee || employee.id === c.actorId) return fail("You cannot act on your own lifecycle plan.");
      let status: LifecyclePlan["status"];
      let employeeStatus = employee.status;
      if (action === "approve") {
        if (plan.status !== "Pending" || plan.proposedBy === c.actorId) return fail("A different reviewer must approve a pending plan.");
        status = "Approved";
      } else if (action === "execute") {
        if (plan.status !== "Approved" || employee.status !== plan.before) return fail("Execution requires approval and an unchanged employee state.");
        status = "Executed"; employeeStatus = plan.mode === "onboarding" ? "Active" : "Offboarding";
      } else if (action === "reverse") {
        if (plan.status !== "Executed" || employee.status !== (plan.mode === "onboarding" ? "Active" : "Offboarding")) return fail("Only executed plans with unchanged results can be reversed.");
        status = "Reversed"; employeeStatus = plan.before;
      } else return fail("Invalid lifecycle action.");
      save(c.org, { ...c.state, plans: c.state.plans.map((p) => p.id === id ? { ...p, status, ...(action === "approve" ? { approvedBy: c.actorId } : {}) } : p), employees: c.state.employees.map((e) => e.id === employee.id ? { ...e, status: employeeStatus } : e) }, `Lifecycle ${action} (demo records only; no provider changes)`, id, c.actorId);
      return { ok: true };
    },
    saveOrganization: (name, domain) => {
      const c = context();
      if (c.role !== "owner") return fail("Only the owner can edit organization identity.");
      if (name.trim().length < 2 || name.length > 100 || !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/i.test(domain.trim())) return fail("Enter a name of 2–100 characters and a valid domain.");
      save(c.org, { ...c.state, org: { ...c.state.org, name: name.trim(), domain: domain.trim().toLowerCase() } }, "Organization identity updated (demo; domain unverified)", c.org, c.actorId);
      return { ok: true };
    },
    setBudget: (department, amount) => {
      const c = context();
      if (c.role !== "owner") return fail("Only the owner can allocate department budgets.");
      if (!departments.includes(department) || !Number.isFinite(amount) || amount < 0 || amount > 1e9 || Math.abs(Math.round(amount * 100) - amount * 100) > 0.000001) return fail("Choose a department and an amount from 0 to 1 billion with at most two decimal places.");
      save(c.org, { ...c.state, budgets: { ...c.state.budgets, [department]: amount } }, "Department budget allocated (simulated USD)", department, c.actorId);
      return { ok: true };
    },
    addEmployee: (input) => {
      const c = context();
      if (!["owner", "hr"].includes(c.role)) return fail("Only HR and the owner can create employee records.");
      if (!["hr", "senior-dev", "junior-dev", "security-analyst"].includes(input.appRole) || (input.appRole === "hr" && c.role !== "owner")) return fail("Only the owner can add HR; owner creation is not supported.");
      if (input.name.trim().length < 2 || input.name.length > 100 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.email) || !input.title.trim() || !departments.includes(input.department)) return fail("Enter a valid name, email, title, department and role.");
      if (c.state.employees.some((e) => e.email.toLowerCase() === input.email.trim().toLowerCase())) return fail("This email already has an employee record.");
      const employee: Employee = { id: `DEMO-${crypto.randomUUID()}`, name: input.name.trim(), email: input.email.trim(), role: input.title.trim(), department: input.department, appRole: input.appRole, status: "Onboarding", verification: "Not submitted", joinDate: new Date().toISOString().slice(0,10), location: "Not specified", projects: [], trustScore: ["senior-dev", "junior-dev"].includes(input.appRole) ? 20 : null, trustEvents: [], salaryBand: "Unassigned", riskScore: 0 };
      save(c.org, { ...c.state, employees: [...c.state.employees, employee] }, "Employee onboarding record created (simulated; no invitation sent)", employee.id, c.actorId);
      return { ok: true };
    },
    updateEmployee: (id, patch) => {
      const c = context();
      if (!["owner", "hr"].includes(c.role)) return fail("Only HR and the owner can update employee records.");
      const employee = c.state.employees.find((e) => e.id === id);
      if (!employee) return fail("Employee not found in this organization.");
      if (id === c.actorId || employee.appRole === "owner") return fail("You cannot change your own lifecycle or the owner record.");
      if (!departments.includes(patch.department) || !["Active", "On leave", "Onboarding", "Offboarding", "Probation"].includes(patch.status)) return fail("Invalid department or lifecycle status.");
      if (!["hr", "senior-dev", "junior-dev", "security-analyst"].includes(patch.appRole)) return fail("Invalid employee role.");
      if (patch.appRole !== employee.appRole && c.role !== "owner") return fail("Only the owner can change application roles.");
      if (patch.appRole !== employee.appRole && Object.values(tenants[c.org].roleUsers).includes(id)) return fail("Fixed demo identities keep their roles; create a separate employee to demonstrate reassignment.");
      save(c.org, { ...c.state, employees: c.state.employees.map((e) => e.id === id ? { ...e, ...patch } : e) }, "Employee department, role or lifecycle updated (simulated)", id, c.actorId);
      return { ok: true };
    },
  };
});

// Connected mode cannot mutate demo stores or report demo persistence as success.
for(const [name, action] of Object.entries(useAdministration.getState())) {
 if(typeof action!=="function")continue;
 const original=action as (...args:unknown[])=>unknown;
 useAdministration.setState({[name]:(...args:unknown[])=>{
  if(isLive())return name==="log"?undefined:{ok:false,error:"Use the connected server controls for this action. This demo action does not save backend records."};
  return original(...args);
 }});
}
