"use client";
import { isLive } from "@/lib/connected/live-state";
import { mutations, liveResult } from "@/lib/connected/mutations";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { Download, LayoutGrid, List, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Select, Field, Input, Textarea } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Kanban } from "@/components/features/devtrack/kanban";
import { IssueDrawer } from "@/components/features/devtrack/issue-drawer";
import { TaskPriority } from "@/components/features/owner/approvals";
import { useWorkspace } from "@/stores/workspace-store";
import { cn } from "@/lib/utils/cn";
import type { Priority } from "@/lib/types";
import { useDataset } from "@/lib/api";
import { downloadCsv } from "@/lib/export/csv";

function BoardInner() {
  const { employeeName, employees, currentUser } = useDataset();
  const params = useSearchParams();
  const { tasks, projects, sprints, addTask } = useWorkspace();
  const [query, setQuery] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [priorityFilter, setPriorityFilter] = React.useState("all");
  const [view, setView] = React.useState<"board" | "list">("board");
  const [proj, setProj] = React.useState("all");
  const [open, setOpen] = React.useState<string | null>(null);
  const [create, setCreate] = React.useState(params.get("new") === "1");
  const [title, setTitle] = React.useState("");
  const [desc, setDesc] = React.useState("");
  const [prio, setPrio] = React.useState<Priority>("Medium");
  const [assignee, setAssignee] = React.useState("");
  const [targetProj, setTargetProj] = React.useState("");
  const [points, setPoints] = React.useState(3);
  const [sprint, setSprint] = React.useState("Backlog");
  const [due, setDue] = React.useState("");
  const shown = tasks.filter((t) => {
    if (proj !== "all" && t.projectId !== proj) return false;
    if (statusFilter !== "all" && t.status !== statusFilter) return false;
    if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
    const q = query.trim().toLocaleLowerCase();
    return !q || [t.key, t.title, t.description, employeeName(t.assignee), ...t.labels].some((v) => v.toLocaleLowerCase().includes(q));
  });
  const active = projects.filter((p) => ["Active", "At risk"].includes(p.status));
  const targetId = targetProj || active[0]?.id || "";
  const developers = employees.filter((e) => ["senior-dev", "junior-dev"].includes(e.appRole));
  const assigneeId = assignee || developers.find((e) => e.id === currentUser.id)?.id || developers[0]?.id || "";

  return (
    <div>
      <PageHeader title="Board" description="Drag cards between columns or open a task for details." actions={
        <>
          <Select aria-label="Filter by project" value={proj} onChange={(e) => setProj(e.target.value)} className="!h-10 w-52"><option value="all">All projects</option>{active.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
          <div className="flex rounded-xl bg-[#eef1fa] p-1" role="group" aria-label="View"><button onClick={() => setView("board")} aria-pressed={view === "board"} className={cn("flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium", view === "board" ? "bg-white text-indigo shadow-sm" : "text-ink-2")}><LayoutGrid className="size-3.5" />Board</button><button onClick={() => setView("list")} aria-pressed={view === "list"} className={cn("flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium", view === "list" ? "bg-white text-indigo shadow-sm" : "text-ink-2")}><List className="size-3.5" />List</button></div>
          <Button variant="secondary" disabled={!shown.length} onClick={() => downloadCsv("mesh-demo-tasks.csv", ["Key", "Title", "Project", "Status", "Priority", "Assignee", "Sprint", "Due", "Points"], shown.map((t) => [t.key, t.title, projects.find((p) => p.id === t.projectId)?.name ?? t.projectId, t.status, t.priority, employeeName(t.assignee), t.sprint, t.due, t.points]))}><Download /> Export CSV</Button>
          <Button variant="gradient" disabled={isLive()&&currentUser.role!=="senior_developer"} onClick={() => setCreate(true)}><Plus /> New task</Button>
        </>
      } />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-3" /><Input aria-label="Search tasks" placeholder="Search task, key, assignee or label" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
        <Select aria-label="Filter task status" className="w-40" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="all">All statuses</option>{["Backlog", "To do", "In progress", "In review", "Done"].map((v) => <option key={v}>{v}</option>)}</Select>
        <Select aria-label="Filter task priority" className="w-40" value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}><option value="all">All priorities</option>{["Critical", "High", "Medium", "Low"].map((v) => <option key={v}>{v}</option>)}</Select>
        <span className="text-xs text-ink-3" aria-live="polite">{shown.length} of {tasks.length} demo tasks</span>
      </div>
      {shown.length === 0 ? <Card className="p-8 text-center text-sm text-ink-2">No tasks match these filters. Try another search or project.</Card> : view === "board" ? <Kanban tasks={shown} onOpen={setOpen} /> : (
        <Card className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-[13.5px]"><thead><tr className="border-b border-line bg-canvas/70 text-xs text-ink-2">{["Key", "Title", "Status", "Priority", "Assignee", "Sprint"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line">{shown.map((t) => <tr key={t.id} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setOpen(t.id)} onClick={() => setOpen(t.id)} className="cursor-pointer hover:bg-tint-violet/40"><td className="px-4 py-3 font-mono text-xs text-ink-3">{t.key}</td><td className="px-4 py-3 font-medium">{t.title}</td><td className="px-4 py-3"><Badge tone="neutral">{t.status}</Badge></td><td className="px-4 py-3"><TaskPriority task={t} /></td><td className="px-4 py-3"><span className="flex items-center gap-2"><Avatar name={employeeName(t.assignee)} size={24} />{employeeName(t.assignee)}</span></td><td className="px-4 py-3 text-ink-2">{t.sprint}</td></tr>)}</tbody></table></Card>
      )}
      <IssueDrawer taskId={open} onClose={() => setOpen(null)} />
      <Dialog open={create} onOpenChange={setCreate}>
        <DialogContent title="Create task" description="Add work to the backlog and assign it.">
          <form className="space-y-4" onSubmit={async (e) => {
            e.preventDefault();
            if (title.trim().length < 3) return;
            const p = projects.find((x) => x.id === targetId);
            if (!p || !active.some((item) => item.id === p.id)) { toast.error("Select an active project first"); return; }
            const unique = crypto.randomUUID();
            const payload={ id: `T-${unique}`, key: `${p.key}-${unique.slice(0, 8).toUpperCase()}`, title: title.trim(), description: desc || "No description yet.", status: "To do", priority: prio, assignee: assigneeId, projectId: targetId, points, labels: ["new"], sprint: sprint.trim() || "Backlog", due, comments: [] };
            const result = isLive()?await liveResult(()=>mutations.addTask(payload as import("@/lib/types").Task)):addTask(payload as import("@/lib/types").Task);
            if (!result.ok) { toast.error(result.error); return; }
            toast.success(isLive()?"Task saved":"Task created (simulated)", { description: `Assigned to ${employeeName(assigneeId)}` });
            setTitle(""); setDesc(""); setCreate(false);
          }}>
            <Field label="Title" htmlFor="ttitle"><Input id="ttitle" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What needs to happen?" required minLength={3} /></Field>
            <Field label="Description" htmlFor="tdesc"><Textarea disabled={isLive()} id="tdesc" value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Project" htmlFor="tproj"><Select id="tproj" value={targetId} onChange={(e) => setTargetProj(e.target.value)}>{active.map((p) => <option key={p.id} value={p.id}>{p.key}</option>)}</Select></Field>
              <Field label="Priority" htmlFor="tprio"><Select disabled={isLive()} id="tprio" value={prio} onChange={(e) => setPrio(e.target.value as Priority)}>{["Critical", "High", "Medium", "Low"].map((p) => <option key={p}>{p}</option>)}</Select></Field>
              <Field label={isLive()?"Assignee account reference":"Assignee"} htmlFor="tassn">{isLive()?<Input id="tassn" value={assigneeId} onChange={e=>setAssignee(e.target.value)} pattern="[a-fA-F0-9-]{36}" required/>:<Select id="tassn" value={assigneeId} onChange={(e) => setAssignee(e.target.value)}>{developers.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select>}</Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Story points" htmlFor="tpoints"><Input disabled={isLive()} id="tpoints" type="number" min={0} max={100} required value={points} onChange={(e) => setPoints(Number(e.target.value))} /></Field>
              <Field label="Sprint" htmlFor="tsprint"><Select disabled={isLive()} id="tsprint" value={sprint} onChange={(e) => setSprint(e.target.value)}><option>Backlog</option>{sprints.filter((s) => s.status !== "Completed").map((s) => <option key={s.id} value={s.id}>{s.name||s.id}</option>)}</Select></Field>
              <Field label="Due date" htmlFor="tdue"><Input disabled={isLive()} id="tdue" type="date" required={!isLive()} value={due} onChange={(e) => setDue(e.target.value)} /></Field>
            </div>
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setCreate(false)}>Cancel</Button><Button type="submit" variant="gradient" disabled={!targetId || !assigneeId||(isLive()&&currentUser.role!=="senior_developer")}>Create task</Button></div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function BoardPage() {
  return <React.Suspense fallback={null}><BoardInner /></React.Suspense>;
}
