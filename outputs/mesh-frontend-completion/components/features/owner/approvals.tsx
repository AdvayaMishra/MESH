"use client";
import { isLive } from "@/lib/connected/live-state";
import { mutations, liveResult } from "@/lib/connected/mutations";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { CalendarClock, Check, CheckCircle2, ChevronRight, X } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarStack } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtCurrency, fmtDate } from "@/lib/utils/format";
import type { Priority, Project } from "@/lib/types";
import { useDataset } from "@/lib/api";

export const priorityTone: Record<Priority, "coral" | "amber" | "sky" | "neutral"> = {
  Critical: "coral",
  High: "amber",
  Medium: "sky",
  Low: "neutral",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge tone={priorityTone[priority]} dot>{priority}</Badge>;
}

export function AwaitingApprovals({ limit }: { limit?: number }) {
  const { employeeName } = useDataset();
  const { projects, setProjectStatus } = useWorkspace();
  const pending = projects.filter((p) => p.status === "Awaiting approval");
  const shown = limit ? pending.slice(0, limit) : pending;
  const [decision, setDecision] = React.useState<{ project: Project; kind: "approve" | "reject" } | null>(null);

  return (
    <Card className="h-full">
      <CardHeader
        title="Awaiting your approval"
        subtitle="Proposals from senior and junior developers"
        action={pending.length > 0 ? <Badge tone="violet">{pending.length} pending</Badge> : undefined}
      />
      <CardBody className="space-y-3">
        {shown.length === 0 && (
          <EmptyState title="You're all caught up" description="New project proposals appear here for a decision." />
        )}
        {shown.map((p) => (
          <div key={p.id} className="rounded-2xl border border-line bg-canvas/60 p-4 transition-colors hover:border-violet/30">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/devtrack/projects/${p.id}`} className="font-display text-[15px] font-semibold text-ink hover:text-indigo">
                    {p.name}
                  </Link>
                  {!isLive()&&<PriorityBadge priority={p.priority} />}
                </div>
                <p className="mt-1 line-clamp-2 text-[13px] text-ink-2">{p.description}</p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-2">
              <span className="flex items-center gap-1.5">
                <Avatar name={employeeName(p.proposedBy ?? p.lead)} size={22} />
                {employeeName(p.proposedBy ?? p.lead)}
              </span>
              <span>Budget {fmtCurrency(p.budget)}</span>
              <span className="flex items-center gap-1"><CalendarClock className="size-3.5" /> Due {fmtDate(p.dueDate)}</span>
              <span>{p.cloud}</span>
            </div>
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="success" onClick={() => setDecision({ project: p, kind: "approve" })}>
                <Check /> Approve
              </Button>
              <Button size="sm" variant="outlineDanger" onClick={() => setDecision({ project: p, kind: "reject" })}>
                <X /> Reject
              </Button>
              <Button size="sm" variant="ghost" asChild>
                <Link href={`/devtrack/projects/${p.id}`}>Details <ChevronRight /></Link>
              </Button>
            </div>
          </div>
        ))}
        {limit && pending.length > limit && (
          <Link href="/owner/projects" className="block text-center text-[13px] font-medium text-indigo hover:underline">
            View all {pending.length} proposals
          </Link>
        )}
      </CardBody>

      <ConfirmDialog
        open={!!decision}
        onOpenChange={(o) => !o && setDecision(null)}
        title={decision?.kind === "approve" ? `Approve ${decision?.project.name}?` : `Reject ${decision?.project.name}?`}
        description={isLive()?"The backend validates independent review, authorization and the saved project state before recording your decision.":
          decision?.kind === "approve"
            ? `This moves the demo project to Active. No funds are allocated or notifications sent.`
            : "The decision and your note are recorded in the demo. No notification is sent."
        }
        confirmLabel={decision?.kind === "approve" ? "Approve project" : "Reject proposal"}
        tone={decision?.kind === "approve" ? "success" : "danger"}
        requireNote={decision?.kind === "reject" ? "Reason for rejection" : undefined}
        onConfirm={async (note) => {
          if (!decision) return;
          const result = isLive()?await liveResult(()=>mutations.setProjectStatus(decision.project.id, decision.kind === "approve" ? "Active" : "Rejected", note)):setProjectStatus(decision.project.id, decision.kind === "approve" ? "Active" : "Rejected", note);
          if (!result.ok) { toast.error(result.error); return false; }
          toast.success(decision.kind === "approve" ? "Project approved" : "Proposal rejected", {
            description: `${decision.project.name} · recorded in the approval history`,
          });
        }}
      />
    </Card>
  );
}

export function ActiveProjectsCard({ limit = 5 }: { limit?: number }) {
  const { employeeName } = useDataset();
  const projects = useWorkspace((s) => s.projects).filter((p) => ["Active", "At risk"].includes(p.status)).slice(0, limit);
  return (
    <Card className="h-full">
      <CardHeader title="Active projects" subtitle="Progress and budget burn" action={<Link href="/devtrack/projects" className="text-[13px] font-medium text-indigo hover:underline">View all</Link>} />
      <CardBody className="space-y-4">
        {projects.map((p) => {
          const burn = Math.round((p.spent / p.budget) * 100);
          return (
            <Link key={p.id} href={`/devtrack/projects/${p.id}`} className="block rounded-xl p-2 -m-2 transition-colors hover:bg-canvas">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium text-ink">{p.name}</p>
                  <p className="text-xs text-ink-3">{p.key} · {employeeName(p.lead)}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <AvatarStack names={p.members.map(employeeName)} size={24} max={3} />
                  {p.status === "At risk" ? <Badge tone="coral" dot>At risk</Badge> : !isLive()?<PriorityBadge priority={p.priority} />:null}
                </div>
              </div>
              <div className="mt-2.5 flex items-center gap-3">
                <Progress value={p.progress} accent={p.status === "At risk" ? "coral" : "violet"} label={`${p.name} progress`} />
                <span className="w-10 shrink-0 text-right text-xs font-semibold text-ink">{p.progress}%</span>
              </div>
              <p className="mt-1 text-[11px] text-ink-3">Budget {burn}% used</p>
            </Link>
          );
        })}
        {projects.length === 0 && <EmptyState title="No active projects" description="Approved proposals show up here." />}
      </CardBody>
    </Card>
  );
}

export function ApprovalHistoryCard() {
  const history = useWorkspace((s) => s.approvalHistory);
  const projects = useWorkspace((s) => s.projects);
  const rows = Object.entries(history)
    .flatMap(([pid, items]) => items.map((h) => ({ ...h, project: projects.find((p) => p.id === pid)?.name ?? pid })))
    .sort((a, b) => b.at.localeCompare(a.at));
  return (
    <Card>
      <CardHeader title="Approval history" subtitle="Every decision is recorded with a note" />
      <CardBody>
        {rows.length === 0 ? (
          <EmptyState title="No decisions yet" />
        ) : (
          <ul className="space-y-3">
            {rows.map((r) => (
              <li key={r.id} className="flex gap-3">
                <span className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full ${r.action === "Rejected" ? "bg-tint-coral text-[#c21d45]" : "bg-tint-mint text-[#008068]"}`}>
                  {r.action === "Rejected" ? <X className="size-3.5" /> : <CheckCircle2 className="size-3.5" />}
                </span>
                <div className="min-w-0 text-[13px]">
                  <p className="text-ink">
                    <span className="font-medium">{r.by}</span> {r.action.toLowerCase()} <span className="font-medium">{r.project}</span>
                  </p>
                  <p className="text-ink-2">“{r.note}”</p>
                  <p className="mt-0.5 text-[11px] text-ink-3">{fmtDate(r.at)}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

export function TaskPriority({task}:{task:import("@/lib/types").Task}){return task.metadataKnown===false?<Badge tone="neutral">Priority unavailable</Badge>:<PriorityBadge priority={task.priority}/>;}
