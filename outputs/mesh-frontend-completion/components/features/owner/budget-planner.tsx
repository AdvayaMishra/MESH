"use client";
import { toast } from "sonner";
import { departments, useAdministration } from "@/stores/admin-store";
import { useTenant } from "@/stores/tenant-store";
import { useDataset } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { fmtCurrency } from "@/lib/utils/format";
import type { Department } from "@/lib/types";
export function BudgetPlanner() {
  const org = useTenant((s) => s.orgId);
  const budgets = useAdministration((s) => s.organizations[org]?.budgets);
  const setBudget = useAdministration((s) => s.setBudget);
  const { employees } = useDataset();
  return <Card><CardHeader title="Department budget allocation" subtitle="Manual monthly USD planning amounts. These do not change actual cloud bills or payroll." /><CardBody className="space-y-4">
    <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const result = setBudget(String(f.get("department")) as Department, Number(f.get("amount"))); if (result.ok) toast.success("Department budget saved (demo)"); else toast.error(result.error); }}>
      <Field label="Budget department" htmlFor="budget-department"><Select id="budget-department" name="department">{departments.map((d) => <option key={d}>{d}</option>)}</Select></Field>
      <Field label="Monthly budget (USD)" htmlFor="budget-amount"><Input id="budget-amount" name="amount" type="number" min={0} max={1000000000} step="0.01" required /></Field>
      <Button type="submit" variant="gradient">Allocate budget</Button>
    </form>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{departments.map((department) => <div key={department} className="rounded-xl border border-line p-3"><p className="text-sm font-semibold">{department}</p><p className="text-xl font-bold">{budgets?.[department] === undefined ? "Not allocated" : fmtCurrency(budgets[department]!)}</p><p className="text-xs text-ink-3">{employees.filter((e) => e.department === department).length} employee records</p></div>)}</div>
  </CardBody></Card>;
}
