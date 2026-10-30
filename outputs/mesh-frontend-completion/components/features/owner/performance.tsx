"use client";
import { isLive } from "@/lib/connected/live-state";
import { DataUnavailable } from "@/lib/connected/finance";
import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { TrustStars } from "@/components/features/stat-pill";
import { RecordTrustEvent, TrustExplainer, TrustHistory, TrustSummary } from "@/components/features/trust-panel";
import { ChartTooltip, Legend, axisProps } from "@/components/charts/chart-kit";
import { colors } from "@/lib/design-tokens";
import type { Employee } from "@/lib/types";
import { scoreFromEvents } from "@/lib/trust";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";

const weekly = [
  { week: "W37", commits: 212, prs: 31, tasks: 44 },
  { week: "W38", commits: 236, prs: 35, tasks: 48 },
  { week: "W39", commits: 198, prs: 29, tasks: 41 },
  { week: "W40", commits: 251, prs: 38, tasks: 52 },
  { week: "W41", commits: 244, prs: 36, tasks: 55 },
  { week: "W42", commits: 267, prs: 41, tasks: 58 },
  { week: "W43", commits: 189, prs: 27, tasks: 49 },
];

export function TeamActivityCard() {
  if(isLive())return <DataUnavailable title="Team activity" reason="Historical commit and pull-request activity is not supplied by the current backend."/>;
  return (
    <Card className="h-full">
      <CardHeader
        title="Team activity"
        subtitle="Seeded historical illustration of commits and pull requests"
        action={<Legend items={[{ label: "Commits", color: colors.violet }, { label: "Pull requests", color: colors.mint }]} />}
      />
      <CardBody>
        <div className="h-60 w-full" role="img" aria-label="Bar chart of weekly commits and pull requests">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={weekly} margin={{ left: -18, right: 4, top: 8 }}>
              <CartesianGrid vertical={false} stroke="#EEF1FA" />
              <XAxis dataKey="week" {...axisProps} />
              <YAxis {...axisProps} />
              <Tooltip cursor={{ fill: "rgba(99,91,255,0.05)" }} content={<ChartTooltip />} />
              <Bar dataKey="commits" name="Commits" fill={colors.violet} radius={[6, 6, 0, 0]} barSize={14} />
              <Bar dataKey="prs" name="Pull requests" fill={colors.mint} radius={[6, 6, 0, 0]} barSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] text-ink-3">W43 is a partial week (data through Oct 23).</p>
      </CardBody>
    </Card>
  );
}

export function TaskCompletionCard() {
  return (
    <Card className="h-full">
      <CardHeader title="Task completion trend" subtitle="Seeded historical illustration; current task changes are shown in the contribution table" />
      <CardBody>
        <div className="h-60 w-full" role="img" aria-label="Area chart of tasks completed per week">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={weekly} margin={{ left: -18, right: 4, top: 8 }}>
              <defs>
                <linearGradient id="taskFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colors.sky} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={colors.sky} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="#EEF1FA" />
              <XAxis dataKey="week" {...axisProps} />
              <YAxis {...axisProps} />
              <Tooltip content={<ChartTooltip />} />
              <Area dataKey="tasks" name="Tasks closed" stroke={colors.sky} strokeWidth={3} fill="url(#taskFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardBody>
    </Card>
  );
}

export function TrustDetailDialog({ employee, onClose }: { employee: Employee | null; onClose: () => void }) {
  return (
    <Dialog open={!!employee} onOpenChange={(o) => !o && onClose()}>
      {employee && (
        <DialogContent side="right" title={`${employee.name} · Trust Stars`} description={`${employee.role} · ${employee.department}`}>
          <div className="space-y-5">
            <div className="flex items-center gap-4 rounded-2xl bg-canvas p-4">
              <Avatar name={employee.name} size={52} />
              <div className="min-w-0 flex-1"><TrustSummary employee={employee} /></div>
            </div>
            <TrustExplainer />
            <div>
              <h4 className="mb-3 font-display text-sm font-semibold">Event history</h4>
              <TrustHistory employee={employee} />
            </div>
            <RecordTrustEvent employee={employee} />
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}

function DemoTrustBoardCard({ limit = 6 }: { limit?: number }) {
  const { employees } = useDataset();
  const [selected, setSelected] = React.useState<Employee | null>(null);
  const reviewed = useWorkspace((s) => s.trustEvents);
  const rows = employees.filter((e) => e.trustScore !== null).map((e) => ({ ...e, trustScore: scoreFromEvents([...(reviewed[e.id] ?? []), ...e.trustEvents]) })).sort((a, b) => (b.trustScore ?? 0) - (a.trustScore ?? 0)).slice(0, limit);
  return (
    <Card className="h-full">
      <CardHeader title="Trust Stars" subtitle="Contextual signal with explainable history" action={<Badge tone="violet">Decision support</Badge>} />
      <CardBody className="space-y-4">
        <TrustExplainer compact />
        <ul className="divide-y divide-line">
          {rows.map((e) => (
            <li key={e.id} className="flex items-center gap-3 py-2.5">
              <Avatar name={e.name} size={34} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium text-ink">{e.name}</p>
                <p className="truncate text-xs text-ink-3">{e.role}</p>
              </div>
              <TrustStars score={e.trustScore ?? 0} />
              <Button size="sm" variant="ghost" onClick={() => setSelected(e)} aria-label={`View ${e.name}'s Trust Stars history`}>
                History
              </Button>
            </li>
          ))}
        </ul>
      </CardBody>
      <TrustDetailDialog employee={selected} onClose={() => setSelected(null)} />
    </Card>
  );
}

export function ContributionTable() {
  const { employees, tasks, pullRequests } = useDataset();
  const rows = employees
    .filter((e) => ["senior-dev", "junior-dev"].includes(e.appRole) && e.projects.length > 0)
    .slice(0, 8)
    .map((e) => ({ e, prs: pullRequests.filter((pr) => pr.author === e.id && pr.status === "Merged").length, tasks: tasks.filter((task) => task.assignee === e.id && task.status === "Done").length }));
  return (
    <Card>
      <CardHeader title="Contribution metrics" subtitle="Counts from current demo tasks and pull requests. Commit history is not supplied. Reviews, mentoring and incident work need separate context." />
      <CardBody className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-[13px]">
          <thead>
            <tr className="text-xs text-ink-3">
              <th className="pb-2 font-medium">Person</th>
              <th className="pb-2 font-medium">Commits</th>
              <th className="pb-2 font-medium">PRs merged</th>
              <th className="pb-2 font-medium">Tasks closed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map(({ e, prs, tasks }) => (
              <tr key={e.id}>
                <td className="py-2.5">
                  <span className="flex items-center gap-2.5"><Avatar name={e.name} size={28} /><span className="font-medium text-ink">{e.name}</span></span>
                </td>
                <td className="py-2.5">
                  <span className="text-xs text-ink-3">Not supplied</span>
                </td>
                <td className="py-2.5">{prs}</td>
                <td className="py-2.5">{tasks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

export { TrustExplainer };

export function TrustBoardCard(props:{limit?:number}){return isLive()?<DataUnavailable title="Trust Stars" reason="Open Workspace Trust to load an authorized reviewed score; a company ranking is not inferred."/>:<DemoTrustBoardCard {...props}/>;}
