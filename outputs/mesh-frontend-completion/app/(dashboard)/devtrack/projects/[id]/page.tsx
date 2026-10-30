"use client";
import { ProjectAllocation } from "@/components/features/devtrack/project-allocation";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, X } from "lucide-react";
import { toast } from "sonner";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarStack } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PriorityBadge } from "@/components/features/owner/approvals";
import { Kanban } from "@/components/features/devtrack/kanban";
import { IssueDrawer } from "@/components/features/devtrack/issue-drawer";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";
import { fmtCurrency, fmtDate, timeAgo } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";

export default function ProjectDetailPage() {
  const { employeeName, roleUsers } = useDataset();
  const { id } = useParams<{ id: string }>();
  const { projects, tasks, sprints, approvalHistory, setProjectStatus, findings } = useWorkspace();
  const role = useUI((s) => s.role);
  const [open, setOpen] = React.useState<string | null>(null);
  const [dlg, setDlg] = React.useState<"approve" | "reject" | null>(null);
  const p = projects.find((x) => x.id === id);
  if (!p) return <EmptyState title="Project not found" description={`There is no project with ID ${id}.`} action={<Button variant="secondary" asChild><Link href="/devtrack/projects">Back to projects</Link></Button>} />;

  const pt = tasks.filter((t) => t.projectId === p.id);
  const done = pt.filter((t) => t.status === "Done").length;
  const history = approvalHistory[p.id] ?? [];
  const projFindings = findings.filter((f) => p.repos.includes(f.repo) && f.status !== "Fixed");
  const activity = [
    ...pt.flatMap((t) => t.comments.map((c) => ({ at: c.at, who: c.author, what: `commented on ${t.key}` }))),
    ...history.map((h) => ({ at: h.at, who: roleUsers.owner, what: `${h.action.toLowerCase()} the project` })),
    { at: "2026-10-22T08:00:00Z", who: p.lead, what: "updated the project plan" },
  ].sort((a, b) => b.at.localeCompare(a.at));
  const canDecide = p.status === "Awaiting approval" && role === "owner";

  return (
    <div className="space-y-6">
      <Link href="/devtrack/projects" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 hover:text-ink"><ArrowLeft className="size-4" /> Projects</Link>
      <Card className="p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 max-w-2xl">
            <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-ink-3">{p.key}</span><Badge tone={p.status === "Active" ? "mint" : p.status === "At risk" ? "coral" : p.status === "Awaiting approval" ? "violet" : "neutral"} dot>{p.status}</Badge><PriorityBadge priority={p.priority} /></div>
            <h1 className="mt-2 font-display text-2xl font-bold sm:text-3xl">{p.name}</h1>
            <p className="mt-2 text-[15px] text-ink-2">{p.description}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <AvatarStack names={p.members.map(employeeName)} size={34} />
            {canDecide && <><Button variant="success" onClick={() => setDlg("approve")}><Check /> Approve</Button><Button variant="outlineDanger" onClick={() => setDlg("reject")}><X /> Reject</Button></>}
          </div>
        </div>
        <dl className="mt-6 grid gap-4 border-t border-line pt-5 sm:grid-cols-2 lg:grid-cols-5">
          {[["Lead", employeeName(p.lead)], ["Budget", fmtCurrency(p.budget)], ["Spent", fmtCurrency(p.spent)], ["Due", fmtDate(p.dueDate)], ["Cloud", p.cloud]].map(([k, v]) => <div key={k}><dt className="text-xs text-ink-3">{k}</dt><dd className="mt-0.5 font-medium">{v}</dd></div>)}
        </dl>
        <div className="mt-5 flex items-center gap-3"><Progress value={p.progress} accent={p.status === "At risk" ? "coral" : "sky"} label="Project progress" /><span className="text-sm font-semibold">{p.progress}%</span></div>
      </Card>

      <Tabs defaultValue="board">
        <TabsList>{[["board", "Board"], ["timeline", "Sprint timeline"], ["security", "Security"], ["approvals", "Approval history"], ["activity", "Activity"]].map(([v, l]) => <TabsTrigger key={v} value={v}>{l}</TabsTrigger>)}</TabsList>
        <TabsContent value="board">{pt.length === 0 ? <Card><EmptyState title="No tasks yet" description="Tasks appear once this project is approved and planned." /></Card> : <Kanban tasks={pt} onOpen={setOpen} />}<p className="mt-3 text-xs text-ink-3">{done} of {pt.length} tasks done</p></TabsContent>
        <TabsContent value="timeline">
          <Card><CardHeader title="Sprint timeline" subtitle="Work scheduled across the next four sprints" /><CardBody className="space-y-3">
            {sprints.map((sp) => {
              const s = sp.id;
              const st = pt.filter((t) => t.sprint === s);
              return (
                <div key={s} className="grid items-center gap-3 sm:grid-cols-[150px_1fr]">
                  <div><p className="text-sm font-semibold">{s}</p><p className="text-xs text-ink-3">{fmtDate(sp.start, { month: "short", day: "numeric" })} – {fmtDate(sp.end, { month: "short", day: "numeric" })}</p></div>
                  <div className={cn("flex min-h-12 flex-wrap items-center gap-2 rounded-xl border border-dashed border-line-strong p-2", sp.status === "Active" && "border-sky bg-tint-sky/50")}>
                    {st.length === 0 && <span className="px-2 text-xs text-ink-3">No tasks scheduled</span>}
                    {st.map((t) => <button key={t.id} onClick={() => setOpen(t.id)} className={cn("rounded-lg px-2.5 py-1.5 text-xs font-medium text-white", t.status === "Done" ? "bg-mint" : t.priority === "Critical" ? "bg-coral" : "bg-violet")}>{t.key}</button>)}
                  </div>
                </div>
              );
            })}
          </CardBody></Card>
        </TabsContent>
        <TabsContent value="security">
          <Card><CardHeader title="Open security findings" subtitle={p.repos.length ? p.repos.join(", ") : "No repositories linked yet"} /><CardBody>
            {projFindings.length === 0 ? <EmptyState title="No open findings" description="Findings from authorized repositories show here." className="!py-6" /> : <ul className="divide-y divide-line">{projFindings.map((f) => <li key={f.id} className="flex items-center gap-3 py-3 text-sm"><span className="min-w-0 flex-1 truncate font-medium">{f.title}</span><Badge tone="neutral">{f.scanner}</Badge><Badge tone={f.severity === "critical" ? "coral" : f.severity === "high" ? "amber" : "sky"} dot>{f.severity}</Badge></li>)}</ul>}
          </CardBody></Card>
        </TabsContent>
        <TabsContent value="approvals">
          <Card><CardBody>
            {history.length === 0 && p.status !== "Awaiting approval" ? <EmptyState title="No decisions recorded" /> : (
              <ol className="space-y-4 border-l border-line pl-5">
                {p.proposedBy && <li className="relative"><span className="absolute -left-[26px] top-1 size-3 rounded-full bg-violet ring-4 ring-white" /><p className="text-sm"><span className="font-medium">{employeeName(p.proposedBy)}</span> submitted the proposal</p><p className="text-xs text-ink-3">{fmtDate(p.proposedAt ?? p.dueDate)}</p></li>}
                {p.status === "Awaiting approval" && <li className="relative"><span className="absolute -left-[26px] top-1 size-3 rounded-full bg-amber ring-4 ring-white" /><p className="text-sm font-medium text-[#a86500]">Waiting for the owner’s decision</p></li>}
                {history.map((h) => <li key={h.id} className="relative"><span className={cn("absolute -left-[26px] top-1 size-3 rounded-full ring-4 ring-white", h.action === "Rejected" ? "bg-coral" : "bg-mint")} /><p className="text-sm"><span className="font-medium">{h.by}</span> {h.action.toLowerCase()}</p><p className="text-sm text-ink-2">“{h.note}”</p><p className="text-xs text-ink-3">{timeAgo(h.at)}</p></li>)}
              </ol>
            )}
          </CardBody></Card>
        </TabsContent>
        <TabsContent value="activity">
          <Card><CardBody><ul className="space-y-4">{activity.map((a, i) => <li key={i} className="flex items-center gap-3 text-sm"><Avatar name={employeeName(a.who)} size={30} /><span className="flex-1"><span className="font-medium">{employeeName(a.who)}</span> {a.what}</span><span className="text-xs text-ink-3">{timeAgo(a.at)}</span></li>)}</ul></CardBody></Card>
        </TabsContent>
      </Tabs>

      <IssueDrawer taskId={open} onClose={() => setOpen(null)} />
      <ProjectAllocation projectId={p.id} />
      <ConfirmDialog
        open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}
        title={dlg === "approve" ? `Approve ${p.name}?` : `Reject ${p.name}?`}
        description={dlg === "approve" ? `Records a simulated decision and moves the demo project to Active. No funds are allocated.` : "The decision and note are recorded in the demo. No notification is sent."}
        confirmLabel={dlg === "approve" ? "Approve project" : "Reject proposal"} tone={dlg === "approve" ? "success" : "danger"}
        requireNote={dlg === "reject" ? "Reason for rejection" : undefined}
        onConfirm={(n) => { const result = setProjectStatus(p.id, dlg === "approve" ? "Active" : "Rejected", n); if (result.ok) toast.success(dlg === "approve" ? "Project approved (simulated)" : "Proposal rejected (simulated)"); else toast.error(result.error); }}
      />
    </div>
  );
}
