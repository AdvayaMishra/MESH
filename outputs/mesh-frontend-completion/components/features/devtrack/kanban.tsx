"use client";
import { isLive } from "@/lib/connected/live-state";
import { mutations, liveResult } from "@/lib/connected/mutations";

import * as React from "react";
import { GripVertical, MessageSquare } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { TaskPriority } from "@/components/features/owner/approvals";
import { useWorkspace } from "@/stores/workspace-store";
import { cn } from "@/lib/utils/cn";
import type { Task, TaskStatus } from "@/lib/types";
import { toast } from "sonner";
import { useDataset } from "@/lib/api";

const cols: { s: TaskStatus; bg: string; dot: string }[] = [
  { s: "Backlog", bg: "bg-[#f1f4fb]", dot: "bg-ink-3" },
  { s: "To do", bg: "bg-tint-violet", dot: "bg-violet" },
  { s: "In progress", bg: "bg-tint-amber", dot: "bg-amber" },
  { s: "In review", bg: "bg-tint-sky", dot: "bg-sky" },
  { s: "Done", bg: "bg-tint-mint", dot: "bg-mint" },
];

export function Kanban({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: string) => void }) {
  const { employeeName,currentUser } = useDataset();
  const setTaskStatus = useWorkspace((s) => s.setTaskStatus);
  const [over, setOver] = React.useState<TaskStatus | null>(null);
  const [dragging, setDragging] = React.useState<string | null>(null);

  return (
    <div className="no-scrollbar -mx-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
      <div className={cn("grid min-w-[1060px] gap-3",isLive()?"grid-cols-4":"grid-cols-5")}>
        {cols.filter(c=>!isLive()||c.s!=="Backlog").map((c) => {
          const items = tasks.filter((t) => t.status === c.s);
          return (
            <section
              key={c.s}
              aria-label={`${c.s} column`}
              onDragOver={(e) => { e.preventDefault(); setOver(c.s); }}
              onDragLeave={() => setOver((o) => (o === c.s ? null : o))}
              onDrop={async (e) => {
                e.preventDefault();
                const id = e.dataTransfer.getData("text/plain");
                setOver(null);
                setDragging(null);
                const t = tasks.find((x) => x.id === id);
                if (t && t.status !== c.s) {
                  const result = isLive()?await liveResult(()=>mutations.setTaskStatus(id,c.s)):setTaskStatus(id, c.s);
                  if (result.ok) toast.success(`${t.key} moved to ${c.s}`); else toast.error(result.error);
                }
              }}
              className={cn("rounded-2xl p-2.5 transition-shadow", c.bg, over === c.s && "ring-2 ring-violet/50")}
            >
              <header className="flex items-center justify-between px-1.5 pb-2.5 pt-1">
                <h3 className="flex items-center gap-2 text-[13px] font-semibold text-ink"><span className={cn("size-2 rounded-full", c.dot)} />{c.s}</h3>
                <span className="rounded-full bg-white/80 px-2 py-0.5 text-xs font-medium text-ink-2">{items.length}</span>
              </header>
              <ul className="space-y-2.5">
                {items.map((t) => (
                  <li key={t.id}>
                    <article
                      draggable={!isLive()||currentUser.role==="senior_developer"||(currentUser.role==="junior_developer"&&t.assignee===currentUser.id)}
                      onDragStart={(e) => { e.dataTransfer.setData("text/plain", t.id); setDragging(t.id); }}
                      onDragEnd={() => setDragging(null)}
                      className={cn("group cursor-grab rounded-xl border border-white bg-white p-3 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-card active:cursor-grabbing", dragging === t.id && "opacity-40")}
                    >
                      <button onClick={() => onOpen(t.id)} className="block w-full text-left" aria-label={`Open ${t.key}: ${t.title}`}>
                        <div className="flex items-center justify-between"><span className="font-mono text-[11px] text-ink-3">{t.key}</span><GripVertical className="size-3.5 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" /></div>
                        <p className="mt-1.5 text-[13px] font-medium leading-snug text-ink">{t.title}</p>
                        <div className="mt-2 flex flex-wrap gap-1.5">{t.labels.map((l) => <Badge key={l} tone="neutral" className="!px-2 !text-[10px]">{l}</Badge>)}</div>
                        <div className="mt-3 flex items-center justify-between">
                          <TaskPriority task={t} />
                          <span className="flex items-center gap-2 text-[11px] text-ink-3">{t.comments.length > 0 && <span className="flex items-center gap-1"><MessageSquare className="size-3" />{t.comments.length}</span>}<Avatar name={employeeName(t.assignee)} size={24} /></span>
                        </div>
                      </button>
                    </article>
                  </li>
                ))}
                {items.length === 0 && <li className="rounded-xl border border-dashed border-ink-3/30 px-3 py-6 text-center text-xs text-ink-3">Drop a task here</li>}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
