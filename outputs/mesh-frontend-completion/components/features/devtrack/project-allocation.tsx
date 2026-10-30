"use client";
import * as React from "react";
import { toast } from "sonner";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { useDataset } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";
export function ProjectAllocation({ projectId }: { projectId: string }) {
  const { employees, employeeName } = useDataset();
  const project = useWorkspace((s) => s.projects.find((p) => p.id === projectId));
  const update = useWorkspace((s) => s.setProjectMember);
  const role = useUI((s) => s.role);
  const [employeeId, setEmployeeId] = React.useState("");
  if (!project) return null;
  const canManage = role === "owner" || role === "senior-dev";
  const available = employees.filter((e) => !project.members.includes(e.id) && e.status !== "Onboarding" && e.status !== "Offboarding");
  return <Card><CardHeader title="Project resource allocation" subtitle="Membership changes stay synchronized with employee profiles in this demo." /><CardBody className="space-y-3">
    <ul className="divide-y divide-line">{project.members.map((id) => <li key={id} className="flex items-center justify-between gap-3 py-2 text-sm"><span>{employeeName(id)}{project.lead === id ? " · Lead" : ""}</span>{canManage && project.lead !== id && <Button size="sm" variant="ghost" onClick={() => { const result = update(projectId, id, false); if (!result.ok) toast.error(result.error); }}>Remove member</Button>}</li>)}</ul>
    {canManage && <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const result = update(projectId, employeeId, true); if (result.ok) { setEmployeeId(""); toast.success("Project member allocated (demo)"); } else toast.error(result.error); }}><Select aria-label="Allocate employee" required value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}><option value="">Choose an employee</option>{available.map((e) => <option key={e.id} value={e.id}>{e.name} · {e.department}</option>)}</Select><Button type="submit" variant="secondary" disabled={!employeeId}>Add member</Button></form>}
  </CardBody></Card>;
}
