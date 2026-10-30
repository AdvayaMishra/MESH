"use client";
import {useResource} from "@/lib/connected/security";
import { isLive } from "@/lib/connected/live-state";
import { mutations, liveResult } from "@/lib/connected/mutations";

import * as React from "react";
import Link from "next/link";
import { Send } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { PriorityBadge } from "@/components/features/owner/approvals";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtDate, timeAgo } from "@/lib/utils/format";
import type { TaskStatus, Priority } from "@/lib/types";
import { useDataset } from "@/lib/api";

export const statuses: TaskStatus[] = ["Backlog", "To do", "In progress", "In review", "Done"];

export function IssueDrawer({ taskId, onClose }: { taskId: string | null; onClose: () => void }) {
  return <IssueDrawerContent key={taskId ?? "closed"} taskId={taskId} onClose={onClose} />;
}

function IssueDrawerContent({ taskId, onClose }: { taskId: string | null; onClose: () => void }) {
  const { employees, employeeName, projectById, currentUser } = useDataset();
  const { tasks, sprints, setTaskStatus, assignTask, addComment, updateTask, deleteTask } = useWorkspace();
  const baseTask = tasks.find((t) => t.id === taskId);
  const details=useResource(isLive()&&taskId?`/api/v1/tasks/${taskId}/details`:"");
  const detail=details.data as {id:string;priority:string;deadline:string|null;sprint_id:string|null}|null;
  const task=baseTask&&detail?{...baseTask,priority:({low:"Low",normal:"Medium",high:"High",critical:"Critical"} as Record<string,Priority>)[detail.priority],due:detail.deadline||"",sprint:detail.sprint_id||"",metadataKnown:true}:baseTask;
  const canManageMetadata=!isLive()||currentUser.role==="senior_developer";
  const [text, setText] = React.useState("");
  const [editing, setEditing] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [draft, setDraft] = React.useState(() => ({ title: task?.title ?? "", description: task?.description ?? "", priority: task?.priority ?? "Medium" as Priority, points: task?.points ?? 0, sprint: task?.sprint ?? "", due: task?.due?.slice(0,10) ?? "", labels: task?.labels.join(", ") ?? "" }));
  const devs = employees.filter((e) => ["senior-dev", "junior-dev"].includes(e.appRole) && e.status !== "Onboarding");

  return (
    <Dialog open={!!task} onOpenChange={(o) => !o && onClose()}>
      {task && (
        <DialogContent side="right" title={task.title} description={`${task.key} · ${projectById(task.projectId)?.name}`}>
          <div className="space-y-5">
            <div className="flex justify-end gap-2"><Button variant="outlineDanger" disabled={isLive()} onClick={() => setConfirmDelete(true)}>Delete task</Button><Button variant="secondary" disabled={!canManageMetadata||(isLive()&&!detail)} onClick={() => { if (!editing) setDraft({ title: task.title, description: task.description, priority: task.priority, points: task.points, sprint: task.sprint, due: task.due?.slice(0,10)||"", labels: task.labels.join(", ") }); setEditing((v) => !v); }}>{editing ? "Cancel editing" : "Edit task details"}</Button></div>
            {editing && <form className="space-y-3 rounded-2xl border border-line bg-canvas p-4" onSubmit={async (e) => {
              e.preventDefault();
              if (!isLive()&&(draft.title.trim().length < 3 || !Number.isInteger(draft.points) || draft.points < 0 || draft.points > 100 || !draft.due)) { toast.error("Enter a valid title, due date and points (0–100)"); return; }
              const patch = { title: draft.title.trim(), description: draft.description.trim(), priority: draft.priority, points: draft.points, sprint: draft.sprint.trim() || "Backlog", due: draft.due, labels: [...new Set(draft.labels.split(",").map((v) => v.trim()).filter(Boolean))] };
              const result=isLive()?await liveResult(()=>mutations.updateTask(task.id,{priority:draft.priority,due:draft.due,sprint:draft.sprint})):updateTask(task.id,patch);
              if (!result.ok) { toast.error(result.error); return; }
              setEditing(false); toast.success("Task details updated");
            }}>
              <label className="block text-xs font-medium">Title<Input aria-label="Edit task title" minLength={3} required disabled={isLive()} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
              <label className="block text-xs font-medium">Description<Textarea aria-label="Edit task description" disabled={isLive()} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs font-medium">Priority<Select aria-label="Edit task priority" value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: e.target.value as Priority })}>{["Critical", "High", "Medium", "Low"].map((v) => <option key={v}>{v}</option>)}</Select></label>
                <label className="text-xs font-medium">Points<Input aria-label="Edit task points" type="number" min={0} max={100} required disabled={isLive()} value={draft.points} onChange={(e) => setDraft({ ...draft, points: Number(e.target.value) })} /></label>
                <label className="text-xs font-medium">Sprint<Select aria-label="Edit task sprint" value={draft.sprint} onChange={(e) => setDraft({ ...draft, sprint: e.target.value })}><option>Backlog</option>{sprints.map((s) => <option key={s.id} value={s.id}>{s.name||s.id}</option>)}{draft.sprint !== "Backlog" && !sprints.some((s) => s.id === draft.sprint) && <option>{draft.sprint}</option>}</Select></label>
                <label className="text-xs font-medium">Due date<Input aria-label="Edit task due date" type="date" required={!isLive()} value={draft.due} onChange={(e) => setDraft({ ...draft, due: e.target.value })} /></label>
              </div>
              <label className="block text-xs font-medium">Labels (comma-separated)<Input aria-label="Edit task labels" disabled={isLive()} value={draft.labels} onChange={(e) => setDraft({ ...draft, labels: e.target.value })} /></label>
              <Button type="submit" variant="gradient">Save changes</Button>
            </form>}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <label className="space-y-1.5"><span className="text-xs font-medium text-ink-3">Status</span>
                <Select disabled={isLive()&&!(currentUser.role==="senior_developer"||(currentUser.role==="junior_developer"&&task.assignee===currentUser.id))} value={task.status} onChange={async (e) => { const value=e.target.value as TaskStatus; const result = isLive()?await liveResult(()=>mutations.setTaskStatus(task.id,value)):setTaskStatus(task.id, value); if (result.ok) toast.success(`Moved to ${e.target.value}`); else toast.error(result.error); }} className="!h-10">{statuses.filter(status=>!isLive()||status!=="Backlog").map((s) => <option disabled={isLive()&&s==="Done"&&currentUser.role!=="senior_developer"} key={s}>{s}</option>)}</Select></label>
              <label className="space-y-1.5"><span className="text-xs font-medium text-ink-3">Assignee</span>
                <Select disabled={isLive()} value={task.assignee} onChange={(e) => { const result = assignTask(task.id, e.target.value); if (result.ok) toast.success(`Assigned to ${employeeName(e.target.value)}`); else toast.error(result.error); }} className="!h-10">{devs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select></label>
            </div>
            <div className="flex flex-wrap items-center gap-2"><PriorityBadge priority={task.priority} />{task.labels.map((l) => <Badge key={l} tone="violet">{l}</Badge>)}<Badge tone="neutral">{task.points} pts</Badge><Badge tone="neutral">{task.sprint}</Badge></div>
            <p className="text-sm leading-relaxed text-ink-2">{task.description}</p>
            <p className="text-xs text-ink-3">Due {fmtDate(task.due)} · <Link className="text-indigo hover:underline" href={`/devtrack/projects/${task.projectId}`}>Open project</Link></p>
            <div>
              <h4 className="mb-3 font-display text-sm font-semibold">Comments and activity</h4>
              <ul className="space-y-4">
                {task.comments.length === 0 && <li className="rounded-xl border border-dashed border-line-strong p-4 text-sm text-ink-2">No comments yet. Start the conversation below.</li>}
                {task.comments.map((c) => (
                  <li key={c.id} className="flex gap-3"><Avatar name={employeeName(c.author)} size={30} /><div className="min-w-0 flex-1 rounded-2xl bg-canvas px-3.5 py-2.5"><p className="text-xs"><span className="font-semibold text-ink">{employeeName(c.author)}</span> <span className="text-ink-3">· {timeAgo(c.at)}</span></p><p className="mt-1 text-[13px] text-ink">{c.text}</p></div></li>
                ))}
              </ul>
              <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (!text.trim()) return; const result = addComment(task.id, currentUser.id, text.trim()); if (result.ok) setText(""); else toast.error(result.error); }}>
                <Textarea disabled={isLive()} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a comment…" aria-label="Write a comment" className="!min-h-12" />
                <Button type="submit" size="icon" variant="gradient" aria-label="Send comment" disabled={!text.trim()}><Send /></Button>
              </form>
            </div>
          </div>
          <ConfirmDialog open={confirmDelete} onOpenChange={setConfirmDelete} title="Delete this demo task?" description="This removes the task and its comments from the current demo organization. Tasks linked to pull requests cannot be deleted." confirmLabel="Delete task" tone="danger" onConfirm={() => { const result = deleteTask(task.id); if (result.ok) { toast.success("Task deleted (simulated)"); onClose(); } else toast.error(result.error); }} />
        </DialogContent>
      )}
    </Dialog>
  );
}
