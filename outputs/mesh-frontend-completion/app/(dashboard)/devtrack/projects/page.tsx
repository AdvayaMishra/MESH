"use client";
import {isLive,useLive} from "@/lib/connected/live-state";
import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/features/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AvatarStack } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PriorityBadge } from "@/components/features/owner/approvals";
import { ProposalDialog } from "@/components/features/devtrack/proposal-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtDate } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

const tone = { Active: "mint", "At risk": "coral", Completed: "sky", Rejected: "neutral", "Awaiting approval": "violet", Planning: "neutral" } as const;

function Inner() {
  const currentRole=useLive(s=>s.profile?.role);
  const { employeeName } = useDataset();
  const params = useSearchParams();
  const projects = useWorkspace((s) => s.projects);
  const [tab, setTab] = React.useState("all");
  const [propose, setPropose] = React.useState(params.get("new") === "1");
  const list = projects.filter((p) => tab === "all" || (tab === "active" && ["Active", "At risk"].includes(p.status)) || (tab === "pending" && p.status === "Awaiting approval") || (tab === "done" && ["Completed", "Rejected"].includes(p.status)));
  return (
    <div>
      <PageHeader title="Projects" description="Everything in flight, awaiting approval or finished." actions={<Button variant="gradient" disabled={isLive()&&!["senior_developer","junior_developer"].includes(currentRole||"")} onClick={() => setPropose(true)}><Plus /> Propose project</Button>} />
      <Tabs value={tab} onValueChange={setTab}><TabsList>{[["all", "All"], ["active", "Active"], ["pending", "Awaiting approval"], ["done", "Closed"]].map(([v, l]) => <TabsTrigger key={v} value={v}>{l}</TabsTrigger>)}</TabsList></Tabs>
      {list.length === 0 ? <Card className="mt-4"><EmptyState title="No projects here" description="Try another filter or propose a new project." /></Card> : (
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {list.map((p) => (
            <Link key={p.id} href={`/devtrack/projects/${p.id}`} className="card card-hover block p-5">
              <div className="flex items-start justify-between gap-2"><span className="font-mono text-xs text-ink-3">{p.key}</span><Badge tone={tone[p.status]} dot>{p.status}</Badge></div>
              <h3 className="mt-2 font-display text-[17px] font-semibold">{p.name}</h3>
              <p className="mt-1.5 line-clamp-2 text-[13px] text-ink-2">{p.description}</p>
              <div className="mt-4 flex items-center gap-3"><Progress value={p.progress} accent={p.status === "At risk" ? "coral" : "sky"} label={`${p.name} progress`} /><span className="text-xs font-semibold">{p.progress}%</span></div>
              <div className="mt-4 flex items-center justify-between"><AvatarStack names={p.members.map(employeeName)} size={26} /><div className="flex items-center gap-2 text-xs text-ink-3">{!isLive()&&<PriorityBadge priority={p.priority} />}{fmtDate(p.dueDate, { month: "short", day: "numeric" })}</div></div>
            </Link>
          ))}
        </div>
      )}
      <ProposalDialog open={propose} onOpenChange={setPropose} />
    </div>
  );
}

export default function ProjectsPage() {
  const currentRole=useLive(s=>s.profile?.role); return <React.Suspense fallback={null}><Inner /></React.Suspense>; }
