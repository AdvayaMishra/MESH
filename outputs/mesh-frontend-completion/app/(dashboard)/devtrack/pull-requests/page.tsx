"use client";
import * as React from "react";
import { CheckCircle2, CircleDashed, GitMerge, XCircle } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { timeAgo } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";
import { Input } from "@/components/ui/input";

const tone = { Open: "sky", Approved: "mint", "Changes requested": "amber", Merged: "violet" } as const;

export default function PullRequestsPage() {
  const { employeeName, currentUser } = useDataset();
  const { pullRequests, prReviews, mergePullRequest, reviewPullRequest } = useWorkspace();
  const role = useUI((s) => s.role);
  const [tab, setTab] = React.useState("open");
  const [search, setSearch] = React.useState("");
  const [notes, setNotes] = React.useState<Record<string, string>>({});
  const list = pullRequests.filter((p) => {
    const merged = p.status === "Merged";
    const matches = `${p.id} ${p.title} ${p.repo} ${p.taskKey} ${employeeName(p.author)}`.toLowerCase().includes(search.trim().toLowerCase());
    return matches && (tab === "merged" ? merged : !merged);
  });
  return (
    <div>
      <PageHeader title="Pull requests" description="Review status and automated checks across repositories." />
      <Tabs value={tab} onValueChange={setTab}><TabsList><TabsTrigger value="open">Open</TabsTrigger><TabsTrigger value="merged">Merged</TabsTrigger></TabsList></Tabs>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Input aria-label="Search pull requests" placeholder="Search title, repository, task or author" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <p className="mt-2 text-xs text-ink-3">Reviews and merges are simulations recorded in this demo session. No GitHub changes are made. A senior developer must be an assigned reviewer; authors cannot review their own PR.</p>
      <Card className="mt-4 divide-y divide-line">
        {list.length === 0 && <EmptyState title="No pull requests" description="No pull requests match the selected tab and search." />}
        {list.map((p) => {
          const canReview = p.status !== "Merged" && p.author !== currentUser.id && (role === "owner" || (role === "senior-dev" && p.reviewers.includes(currentUser.id)));
          const canMerge = p.status === "Approved" && (role === "senior-dev" || role === "owner");
          const note = notes[p.id] ?? "";
          const clearNote = () => setNotes((prev) => ({ ...prev, [p.id]: "" }));
          return <div key={`${p.repo}:${p.id}`} className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-4">
              {p.checks === "passing" ? <CheckCircle2 className="size-5 text-mint" aria-label="Checks passing" /> : p.checks === "failing" ? <XCircle className="size-5 text-coral" aria-label="Checks failing" /> : <CircleDashed className="size-5 animate-spin text-sky" aria-label="Checks running" />}
              <div className="min-w-0 flex-1 basis-48"><p className="truncate text-sm font-semibold">{p.title}</p><p className="text-xs text-ink-3">{p.id} · {p.repo} · {p.taskKey} · updated {timeAgo(p.updatedAt)}</p></div>
              <span className="hidden text-xs sm:block"><span className="text-[#008068]">+{p.additions}</span> <span className="text-[#c21d45]">−{p.deletions}</span></span>
              <span className="flex items-center gap-1.5 text-xs text-ink-2"><Avatar name={employeeName(p.author)} size={26} />{employeeName(p.author).split(" ")[0]}</span><Badge tone={tone[p.status]} dot>{p.status}</Badge>
            </div>
            {(canReview || canMerge) && <div className="flex flex-wrap items-center gap-2">
              <Input aria-label={`Review or merge note for ${p.id}`} placeholder="Review or merge note (10+ characters)" value={note} onChange={(e) => setNotes((prev) => ({ ...prev, [p.id]: e.target.value }))} className="min-w-48 flex-1" />
              {canReview && p.status !== "Approved" && <Button size="sm" variant="success" onClick={() => { const result = reviewPullRequest(p.id, "Approved", note); if (result.ok) { toast.success("Review approved (simulated)"); clearNote(); } else toast.error(result.error); }}>Approve</Button>}
              {canReview && p.status !== "Changes requested" && <Button size="sm" variant="outlineDanger" onClick={() => { const result = reviewPullRequest(p.id, "Changes requested", note); if (result.ok) { toast.success("Changes requested (simulated)"); clearNote(); } else toast.error(result.error); }}>Request changes</Button>}
              {canMerge && <Button size="sm" variant="secondary" onClick={() => { const result = mergePullRequest(p.id, note); if (result.ok) { toast.success(`${p.id} merged (simulated)`); clearNote(); } else toast.error(result.error); }}><GitMerge /> Merge</Button>}
            </div>}
            {(prReviews[p.id] ?? []).length > 0 && <details className="text-xs text-ink-2"><summary className="cursor-pointer font-medium">Demo review history ({prReviews[p.id].length})</summary><ul className="mt-2 space-y-2">{prReviews[p.id].map((r) => <li key={r.id}><span className="font-semibold">{r.actor}</span> · {r.decision} · {timeAgo(r.at)}<p>{r.note}</p></li>)}</ul></details>}
          </div>;
        })}
      </Card>
    </div>
  );
}
