"use client";
import * as React from "react";
import { toast } from "sonner";
import { useDataset } from "@/lib/api";
import { useUI } from "@/stores/ui-store";
import { departments, useAdministration } from "@/stores/admin-store";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import type { Department, Employee, Role } from "@/lib/types";

export function EmployeeAdministration() {
  const { employees } = useDataset();
  const role = useUI((s) => s.role);
  const { addEmployee, updateEmployee } = useAdministration();
  const [selected, setSelected] = React.useState(employees.find((e) => e.appRole !== "owner")?.id ?? "");
  const employee = employees.find((e) => e.id === selected);
  return <div className="grid gap-4 xl:grid-cols-2">
    <Card><CardHeader title="Create onboarding record" subtitle="Demo only. No account, email, payroll or external access is created." /><CardBody>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const result = addEmployee({ name: String(f.get("name")), email: String(f.get("email")), title: String(f.get("title")), department: String(f.get("department")) as Department, appRole: String(f.get("role")) as Role }); if (result.ok) { e.currentTarget.reset(); toast.success("Onboarding record created in this demo session"); } else toast.error(result.error); }}>
        <Field label="Employee name" htmlFor="employee-name"><Input id="employee-name" name="name" required minLength={2} maxLength={100} /></Field>
        <Field label="Employee email" htmlFor="employee-email"><Input id="employee-email" name="email" type="email" required /></Field>
        <Field label="Job title" htmlFor="employee-title"><Input id="employee-title" name="title" required maxLength={100} /></Field>
        <Field label="Department" htmlFor="employee-department"><Select id="employee-department" name="department">{departments.map((d) => <option key={d}>{d}</option>)}</Select></Field>
        <Field label="Application role" htmlFor="employee-role"><Select id="employee-role" name="role">{["junior-dev", "senior-dev", "security-analyst", ...(role === "owner" ? ["hr"] : [])].map((r) => <option key={r}>{r}</option>)}</Select></Field>
        <Button type="submit" variant="gradient">Create employee record</Button>
      </form>
    </CardBody></Card>
    <Card><CardHeader title="Employee lifecycle and allocation" subtitle="Changes update directory and profiles. External provisioning requires backend execution." /><CardBody className="space-y-3">
      <Field label="Select employee" htmlFor="admin-employee"><Select id="admin-employee" value={selected} onChange={(e) => setSelected(e.target.value)}>{employees.filter((e) => e.appRole !== "owner").map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></Field>
      {employee && <form key={`${employee.id}:${employee.status}:${employee.appRole}:${employee.department}`} className="space-y-3" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const result = updateEmployee(employee.id, { department: String(f.get("department")) as Department, appRole: String(f.get("role") ?? employee.appRole) as Role, status: String(f.get("status")) as Employee["status"] }); if (result.ok) toast.success("Employee record updated (demo)"); else toast.error(result.error); }}>
        <Field label="Assigned department" htmlFor="assigned-dept"><Select id="assigned-dept" name="department" defaultValue={employee.department}>{departments.map((d) => <option key={d}>{d}</option>)}</Select></Field>
        <Field label="Lifecycle status" htmlFor="employee-status"><Select id="employee-status" name="status" defaultValue={employee.status}>{["Onboarding", "Probation", "Active", "On leave", "Offboarding"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Assigned application role" htmlFor="assigned-role"><Select id="assigned-role" name="role" defaultValue={employee.appRole} disabled={role !== "owner"}>{["hr", "senior-dev", "junior-dev", "security-analyst"].map((r) => <option key={r}>{r}</option>)}</Select></Field>
        <Button type="submit" variant="secondary">Save employee changes</Button>
      </form>}
    </CardBody></Card>
  </div>;
}
