"use client";
import {isLive} from "@/lib/connected/live-state";
import * as React from "react";
import Link from "next/link";
import { Bug, CheckCircle2, Code2, GitPullRequest, ShieldAlert, Sparkles } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { KpiCard } from "@/components/features/kpi-card";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SeverityBadge, SimulatedTag } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { TrustHistory, TrustSummary } from "@/components/features/trust-panel";
import { PriorityBadge, TaskPriority } from "@/components/features/owner/approvals";
import { IssueDrawer } from "@/components/features/devtrack/issue-drawer";
import { ProposalDialog } from "@/components/features/devtrack/proposal-dialog";
import { useUI } from "@/stores/ui-store";
import { useWorkspace } from "@/stores/workspace-store";
import { colors } from "@/lib/design-tokens";
import { fmtDate, timeAgo } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

const prTone = { Open: "sky", Approved: "mint", "Changes requested": "amber", Merged: "violet" } as const;

export default function DevTrackDashboard() {
  const { employees, employeeById, employeeName, currentUser } = useDataset();
  const role = useUI((s) => s.role);
  const senior = role === "senior-dev" || role === "owner" || role === "security-analyst";
  const me = currentUser.id;
  const meEmp = employeeById(me);
  const { tasks, projects, findings, pullRequests, repos } = useWorkspace();
  const [open, setOpen] = React.useState<string | null>(null);
  const [propose, setPropose] = React.useState(false);

  const myTasks = tasks.filter((t) => t.assignee === me && t.status !== "Done");
  const myProjects = projects.filter((p) => p.members.includes(me));
  const myFindings = findings.filter((f) => f.assignee === me && f.status !== "Fixed");
  const pendingProposals = projects.filter((p) => p.status === "Awaiting approval" && p.proposedBy !== me);
  const workload = employees.filter((e) => ["senior-dev", "junior-dev"].includes(e.appRole) && e.projects.length).slice(0, 8).map((e) => ({ name: e.name.split(" ")[0], pts: tasks.filter((t) => t.assignee === e.id && t.status !== "Done").reduce((s, t) => s + (isLive()?1:t.points), 0) }));
  const summary = `You have ${myTasks.length} open tasks, ${myProjects.length} assigned projects and ${myFindings.length} open security findings in your accessible workspace. ${pendingProposals.length} project proposals await an owner decision.`;

  if(!meEmp)return <Card className="p-6">Your employee profile is unavailable. Refresh the workspace or contact HR.</Card>;
  return (
    <div className="space-y-6">
      <PageHeader
        title={senior ? "Senior developer dashboard" : "My workspace"}
        description={`Viewing as ${meEmp.name}. Your role is verified by the backend.`}
        actions={<><Button variant="secondary" asChild><Link href="/devtrack/board">Open board</Link></Button><Button variant="gradient" disabled={isLive()&&!["senior_developer","junior_developer"].includes(currentUser.role)} onClick={() => setPropose(true)}>{senior ? "New project" : "Submit a proposal"}</Button></>}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label={senior ? "Assigned projects" : "My projects"} value={myProjects.length} icon={Code2} accent="sky" variant="gradient" href="/devtrack/projects" />
        <KpiCard label="Open tasks" value={myTasks.length} icon={CheckCircle2} accent="violet" href="/devtrack/board" />
        <KpiCard label={senior ? "Proposals to review" : "Open pull requests"} value={senior ? pendingProposals.length : pullRequests.filter((p) => p.author === me && p.status !== "Merged").length} icon={GitPullRequest} accent="mint" href={senior ? "/devtrack/projects" : "/devtrack/pull-requests"} />
        <KpiCard label="Security findings" value={myFindings.length} icon={ShieldAlert} accent="coral" href="/devtrack/security" />
      </div>

      <Card className="relative overflow-hidden border-violet/20 bg-gradient-to-br from-[#f4f2ff] to-[#eaf6ff] p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl gradient-violet text-white"><Sparkles className="size-5" /></span>
          <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-display text-base font-bold">AI summary</h2><SimulatedTag /></div><p className="mt-1.5 text-[14.5px] leading-relaxed text-ink">{summary}</p></div>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="My tasks" subtitle="Click a task to open details, comments and status" action={<Link href="/devtrack/board" className="text-[13px] font-medium text-indigo hover:underline">View board</Link>} />
          <CardBody>
            {myTasks.length === 0 ? <p className="py-8 text-center text-sm text-ink-2">Nothing assigned. Pick something from the board.</p> : (
              <ul className="divide-y divide-line">{myTasks.map((t) => (
                <li key={t.id}><button onClick={() => setOpen(t.id)} className="flex w-full items-center gap-3 py-3 text-left transition-colors hover:bg-canvas">
                  <span className="font-mono text-xs text-ink-3">{t.key}</span><span className="min-w-0 flex-1 truncate text-sm font-medium">{t.title}</span><Badge tone="neutral">{t.status}</Badge><TaskPriority task={t} /><span className="hidden text-xs text-ink-3 sm:block">{fmtDate(t.due, { month: "short", day: "numeric" })}</span>
                </button></li>
              ))}</ul>
            )}
          </CardBody>
        </Card>
        {senior ? (
          <Card>
            <CardHeader title="Team workload" subtitle="Open story points per developer" />
            <CardBody><div className="h-60" role="img" aria-label="Bar chart of open story points by developer"><ResponsiveContainer width="100%" height="100%"><BarChart data={workload} layout="vertical" margin={{ left: 10, right: 12 }}>
              <CartesianGrid horizontal={false} stroke="#EEF1FA" /><XAxis type="number" {...axisProps} allowDecimals={false} /><YAxis type="category" dataKey="name" {...axisProps} width={56} />
              <Tooltip cursor={{ fill: "rgba(56,189,248,0.08)" }} content={<ChartTooltip />} />
              <Bar dataKey="pts" name="Points" radius={[0, 8, 8, 0]} barSize={14}>{workload.map((w, i) => <Cell key={i} fill={w.pts > 10 ? colors.coral : w.pts > 6 ? colors.amber : colors.sky} />)}</Bar></BarChart></ResponsiveContainer></div></CardBody>
          </Card>
        ) : (
          <Card>
            <CardHeader title="My Trust Stars" subtitle="Decision support, with visible history" />
            <CardBody className="space-y-3">{isLive()?<p className="text-sm text-ink-2"><Link className="underline" href="/workspace/trust">Load your reviewed Trust Stars and history</Link>. Scores are decision support and require human review.</p>:<TrustSummary employee={meEmp} size={22} />}
              {!isLive()&&<TrustHistory employee={meEmp} />}
              <p className="text-xs text-ink-3">Scores are reviewed by people and never judge trustworthiness on their own.</p></CardBody>
          </Card>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title={senior ? "Pending junior developer proposals" : "My proposals and pull requests"} />
          <CardBody>
            {senior ? (
              pendingProposals.length === 0 ? <p className="py-6 text-center text-sm text-ink-2">No proposals waiting for review.</p> : (
                <ul className="space-y-3">{pendingProposals.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-3.5"><Avatar name={employeeName(p.proposedBy ?? p.lead)} size={34} /><div className="min-w-0 flex-1"><Link href={`/devtrack/projects/${p.id}`} className="text-sm font-medium hover:text-indigo">{p.name}</Link><p className="text-xs text-ink-3">by {employeeName(p.proposedBy ?? p.lead)} · proposed {fmtDate(p.proposedAt ?? p.dueDate)}</p></div><PriorityBadge priority={p.priority} />
                    <Button size="sm" variant="soft" onClick={() => { const result = useWorkspace.getState().endorseProject(p.id); if (result.ok) toast.success("Endorsement recorded for owner review (demo)"); else toast.error(result.error); }}>Endorse</Button></li>
                ))}</ul>
              )
            ) : (
              <ul className="divide-y divide-line">{pullRequests.filter((p) => p.author === me).map((p) => (
                <li key={p.id} className="flex items-center gap-3 py-3 text-sm"><span className="font-mono text-xs text-ink-3">{p.id}</span><span className="min-w-0 flex-1 truncate font-medium">{p.title}</span><Badge tone={prTone[p.status]} dot>{p.status}</Badge></li>
              ))}</ul>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Repository health" action={<Link href="/devtrack/security" className="text-[13px] font-medium text-indigo hover:underline">Details</Link>} />
          <CardBody className="space-y-3.5">{repos.slice(0, 5).map((r) => (
            <div key={r.name}><div className="mb-1.5 flex items-center justify-between text-[13px]"><span className="truncate font-medium">{r.name}</span><span className="text-ink-2">{r.health}</span></div><Progress value={r.health} accent={r.health >= 85 ? "mint" : r.health >= 70 ? "amber" : "coral"} label={`${r.name} health`} /></div>
          ))}</CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Security findings assigned" subtitle="Evidence is sanitized. Secret values are never shown." action={<Link href="/devtrack/security" className="text-[13px] font-medium text-indigo hover:underline">All findings</Link>} />
        <CardBody>
          {myFindings.length === 0 ? <p className="py-6 text-center text-sm text-ink-2">No open findings assigned to you.</p> : (
            <ul className="divide-y divide-line">{myFindings.map((f) => <li key={f.id} className="flex flex-wrap items-center gap-3 py-3 text-sm"><Bug className="size-4 text-ink-3" /><span className="min-w-0 flex-1 truncate font-medium">{f.title}</span><span className="font-mono text-xs text-ink-3">{f.repo}</span><SeverityBadge severity={f.severity} /></li>)}</ul>
          )}
        </CardBody>
      </Card>
      {!isLive()&&<p className="text-xs text-ink-3">Last activity {timeAgo("2026-10-23T09:40:00Z")}</p>}
      <IssueDrawer taskId={open} onClose={() => setOpen(null)} />
      <ProposalDialog open={propose} onOpenChange={setPropose} />
    </div>
  );
}
