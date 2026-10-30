"use client";
import Link from "next/link";
import * as React from "react";
import { Search, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { downloadCsv } from "@/lib/export/csv";
import { PageHeader } from "@/components/features/page-header";
import { ActiveProjectsCard, ApprovalHistoryCard, AwaitingApprovals, PriorityBadge } from "@/components/features/owner/approvals";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtCurrency, fmtDate } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

export default function OwnerProjectsPage() {
  const { employeeName } = useDataset();
  const projects = useWorkspace((s) => s.projects);
  const [query, setQuery] = React.useState("");
  const [status, setStatus] = React.useState("all");
  const [priority, setPriority] = React.useState("all");
  const filteredProjects = projects.filter((project) => {
    const term = query.trim().toLocaleLowerCase();
    return (status === "all" || project.status === status)
      && (priority === "all" || project.priority === priority)
      && (!term || [project.name, project.key, employeeName(project.lead)].some((value) => value.toLocaleLowerCase().includes(term)));
  });
  const statusTone = { Active: "mint", "At risk": "coral", Completed: "sky", Rejected: "neutral", "Awaiting approval": "violet", Planning: "neutral" } as const;
  return (
    <div className="space-y-6">
      <PageHeader title="Projects and approvals" description="Decide on proposals, track delivery and review the full approval trail." />
      <div className="grid gap-4 xl:grid-cols-2">
        <AwaitingApprovals />
        <ActiveProjectsCard limit={5} />
      </div>
      <Card>
        <CardHeader title="All projects" subtitle={`${filteredProjects.length} of ${projects.length} projects in the current demo organization`} />
        <div className="flex flex-wrap items-center gap-2 px-5 pb-4">
          <div className="relative min-w-[190px] flex-1">
            <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-3" />
            <Input aria-label="Search projects" placeholder="Search projects, keys or leads" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <Select aria-label="Filter project status" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">All statuses</option>
            {[...new Set(projects.map((p) => p.status))].map((value) => <option key={value} value={value}>{value}</option>)}
          </Select>
          <Select aria-label="Filter project priority" className="w-40" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="all">All priorities</option>
            {[...new Set(projects.map((p) => p.priority))].map((value) => <option key={value} value={value}>{value}</option>)}
          </Select>
          <Button variant="secondary" disabled={!filteredProjects.length} onClick={() => downloadCsv("mesh-demo-owner-projects.csv", ["Project", "Key", "Status", "Priority", "Lead", "Progress (%)", "Budget", "Due date"], filteredProjects.map((p) => [p.name, p.key, p.status, p.priority, employeeName(p.lead), p.progress, p.budget, p.dueDate]))}><Download /> Export filtered CSV</Button>
        </div>
        <p className="px-5 pb-2 text-xs text-ink-3" aria-live="polite">Demo project records only; exports are not official company reports.</p>
        <CardBody className="overflow-x-auto">
          {!filteredProjects.length && <EmptyState title="No matching projects" description="Try a different search or filter." />}
          <table className="w-full min-w-[760px] text-left text-[13px]">
            <thead>
              <tr className="text-xs text-ink-3">
                {["Project", "Status", "Priority", "Lead", "Progress", "Budget", "Due"].map((h) => <th key={h} className="pb-2 pr-4 font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filteredProjects.map((p) => (
                <tr key={p.id} className="transition-colors hover:bg-canvas">
                  <td className="py-3 pr-4"><Link href={`/devtrack/projects/${p.id}`} className="font-medium text-ink hover:text-indigo">{p.name}</Link><div className="text-xs text-ink-3">{p.key}</div></td>
                  <td className="py-3 pr-4"><Badge tone={statusTone[p.status]} dot>{p.status}</Badge></td>
                  <td className="py-3 pr-4"><PriorityBadge priority={p.priority} /></td>
                  <td className="py-3 pr-4">{employeeName(p.lead)}</td>
                  <td className="py-3 pr-4 w-40"><Progress value={p.progress} accent={p.status === "At risk" ? "coral" : "violet"} label={`${p.name} progress`} /></td>
                  <td className="py-3 pr-4">{fmtCurrency(p.budget, true)}</td>
                  <td className="py-3">{fmtDate(p.dueDate, { month: "short", day: "numeric" })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>
      <ApprovalHistoryCard />
    </div>
  );
}
