"use client";
import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Field, Input } from "@/components/ui/input";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";
import { fmtDate } from "@/lib/utils/format";

export default function SprintsPage() {
  const { sprints, tasks, createSprint, setSprintStatus } = useWorkspace();
  const role = useUI((s) => s.role);
  const canManage = role === "owner" || role === "senior-dev";
  const [name, setName] = React.useState("");
  const [start, setStart] = React.useState("");
  const [end, setEnd] = React.useState("");
  return <div className="space-y-5">
    <PageHeader title="Sprint planning" description="Plan demo sprints and assign work from the task board." badge={<SimulatedTag label="Session-only planning" />} />
    {canManage && <Card><CardHeader title="Create sprint" subtitle="Changes are stored in this demo session." /><CardBody><form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); const result = createSprint(name, start, end); if (!result.ok) { toast.error(result.error); return; } setName(""); setStart(""); setEnd(""); toast.success("Sprint created (simulated)"); }}>
      <Field label="Sprint name" htmlFor="sprint-name"><Input id="sprint-name" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Start date" htmlFor="sprint-start"><Input id="sprint-start" type="date" required value={start} onChange={(e) => setStart(e.target.value)} /></Field>
      <Field label="End date" htmlFor="sprint-end"><Input id="sprint-end" type="date" required value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
      <Button type="submit" variant="gradient">Create sprint</Button>
    </form></CardBody></Card>}
    <div className="grid gap-4 lg:grid-cols-2">{sprints.map((s) => {
      const work = tasks.filter((t) => t.sprint === s.id);
      const done = work.filter((t) => t.status === "Done");
      return <Card key={s.id}><CardHeader title={s.id} subtitle={`${fmtDate(s.start)} – ${fmtDate(s.end)}`} action={<Badge tone={s.status === "Active" ? "sky" : s.status === "Completed" ? "mint" : "neutral"}>{s.status}</Badge>} /><CardBody>
        <p className="text-sm text-ink-2">{done.length} of {work.length} tasks done · {work.reduce((n, t) => n + t.points, 0)} planned points{ s.status === "Completed" ? ` · ${s.velocity} completed points` : "" }</p>
        {work.length ? <ul className="mt-3 space-y-1 text-sm">{work.map((t) => <li key={t.id}><span className="font-mono text-xs text-ink-3">{t.key}</span> · {t.title} <span className="text-ink-3">({t.status})</span></li>)}</ul> : <p className="mt-3 text-sm text-ink-3">No tasks assigned to this sprint.</p>}
        <div className="mt-4 flex flex-wrap gap-2"><Button asChild size="sm" variant="secondary"><Link href="/devtrack/board">Open board</Link></Button>{canManage && s.status !== "Completed" && <Button size="sm" variant="soft" onClick={() => { const result = setSprintStatus(s.id, s.status === "Planned" ? "Active" : "Completed"); if (result.ok) toast.success("Sprint updated (simulated)"); else toast.error(result.error); }}>{s.status === "Planned" ? "Start sprint" : "Complete sprint"}</Button>}</div>
      </CardBody></Card>;
    })}</div>
  </div>;
}
