"use client";
import * as React from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";
import { LEAVE_TYPES, validateLeave, weekdaysBetween } from "@/lib/leave";
import { fmtDate } from "@/lib/utils/format";

const tone = (s: string) => (s === "Approved" ? "mint" : s === "Pending" ? "amber" : s === "Rejected" ? "coral" : "neutral") as "mint" | "amber" | "coral" | "neutral";
const blank = { type: "Annual leave", from: "", to: "", reason: "" };

/** "My leave": every role requests leave for themselves and tracks status. Review happens in People (HR/Owner, never self). */
export default function MyLeave() {
  const { currentUser, employeeName } = useDataset();
  const leave = useWorkspace((s) => s.leave);
  const submit = useWorkspace((s) => s.submitLeave);
  const cancel = useWorkspace((s) => s.cancelLeave);
  const [v, setV] = React.useState(blank);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const today = new Date().toISOString().slice(0, 10);
  const mine = leave.filter((l) => l.employee === currentUser.id);
  const days = v.from && v.to && v.to >= v.from ? weekdaysBetween(v.from, v.to) : 0;

  const onSubmit = () => {
    const errs = validateLeave(v, { today, employeeId: currentUser.id, existing: leave });
    setErrors(errs);
    if (Object.keys(errs).length) return;
    const r = submit(v);
    if (!r.ok) { toast.error("Request not submitted", { description: r.error }); return; }
    toast.success(`Leave request ${r.id} submitted`, { description: "Status: Pending HR review." });
    setV(blank);
  };

  return (
    <div>
      <PageHeader title="My leave" description="Request time off and track decisions. Working days only; balances, accrual and payroll effects are not modeled." badge={<SimulatedTag label="Demo workflow" />} />
      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <Card>
          <CardHeader title="New request" subtitle={employeeName(currentUser.id)} />
          <CardBody className="space-y-4">
            <Field label="Type" htmlFor="l-type" error={errors.type}><Select id="l-type" value={v.type} onChange={(e) => setV({ ...v, type: e.target.value })}>{LEAVE_TYPES.map((t) => <option key={t}>{t}</option>)}</Select></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="From" htmlFor="l-from" error={errors.from}><Input id="l-from" type="date" min={today} value={v.from} onChange={(e) => setV({ ...v, from: e.target.value })} aria-invalid={!!errors.from} /></Field>
              <Field label="To" htmlFor="l-to" error={errors.to}><Input id="l-to" type="date" min={v.from || today} value={v.to} onChange={(e) => setV({ ...v, to: e.target.value })} aria-invalid={!!errors.to} /></Field>
            </div>
            <Field label="Note" htmlFor="l-note" error={errors.reason} hint={days ? `${days} working day${days === 1 ? "" : "s"}` : "Optional, except for medical leave."}><Textarea id="l-note" value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} aria-invalid={!!errors.reason} /></Field>
            <Button variant="gradient" onClick={onSubmit}>Submit request</Button>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="My requests" />
          <CardBody>
            {mine.length === 0 ? <EmptyState title="No leave requests yet" description="Submitted requests and their decisions will appear here." /> : (
              <ul className="divide-y divide-line">
                {mine.map((l) => (
                  <li key={l.id} data-testid="my-leave" className="flex flex-wrap items-center gap-3 py-3">
                    <div className="min-w-0 flex-1"><p className="text-sm font-medium">{l.type} <span className="font-mono text-xs text-ink-3">{l.id}</span></p><p className="text-xs text-ink-3">{fmtDate(l.from, { month: "short", day: "numeric", year: "numeric" })} – {fmtDate(l.to, { month: "short", day: "numeric", year: "numeric" })} · {l.days}d{l.reviewedBy ? ` · reviewed by ${employeeName(l.reviewedBy)}` : ""}{l.reviewNote ? ` · “${l.reviewNote}”` : ""}</p></div>
                    <Badge tone={tone(l.status)} dot>{l.status}</Badge>
                    {l.status === "Pending" && <Button size="sm" variant="ghost" onClick={() => { const r = cancel(l.id); if (r.ok) toast("Request cancelled"); else toast.error(r.error); }}>Cancel</Button>}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
