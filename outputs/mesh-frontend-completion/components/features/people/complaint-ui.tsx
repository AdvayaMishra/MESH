"use client";
import * as React from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { COMPLAINT_CATEGORIES, validateComplaint, type ComplaintInput } from "@/lib/complaints";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";
import { fmtDate } from "@/lib/utils/format";
import type { ComplaintEvent, ComplaintStatus } from "@/lib/types";

export const statusTone: Record<ComplaintStatus, "sky" | "amber" | "violet" | "mint" | "neutral"> = { Submitted: "sky", "Under review": "amber", Investigating: "violet", Resolved: "mint", Closed: "neutral", Withdrawn: "neutral" };
export const ComplaintStatusBadge = ({ status }: { status: ComplaintStatus }) => <Badge tone={statusTone[status]} dot>{status}</Badge>;

export function Timeline({ events, name }: { events: ComplaintEvent[]; name: (id: string) => string }) {
  return (
    <ol className="space-y-3 border-l border-line pl-4">
      {[...events].reverse().map((e) => (
        <li key={e.id} className="relative text-[13px]">
          <span className="absolute -left-[21px] top-1.5 size-2 rounded-full bg-violet" />
          <p className="text-xs text-ink-3">{fmtDate(e.at, { month: "short", day: "numeric", year: "numeric" })} · {e.kind}{e.visibility === "hr" ? " · reviewers only" : ""}</p>
          <p className="text-ink-2">{e.text} <span className="text-ink-3">— {e.actor === "system" ? "System" : name(e.actor)}</span></p>
        </li>
      ))}
    </ol>
  );
}

const blank = { title: "", category: "" as ComplaintInput["category"], description: "", incidentDate: "", confidentiality: "Confidential" as ComplaintInput["confidentiality"], anonymous: false, concerning: "" };

export function ComplaintDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { employees, currentUser } = useDataset();
  const submit = useWorkspace((s) => s.submitComplaint);
  const [v, setV] = React.useState(blank);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const today = new Date().toISOString().slice(0, 10);
  const set = <K extends keyof typeof blank>(k: K, val: (typeof blank)[K]) => setV((p) => ({ ...p, [k]: val }));

  const onSubmit = () => {
    const errs = validateComplaint(v, today);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    const res = submit({ ...v, concerning: v.concerning || undefined });
    if (!res.ok) { toast.error("Complaint not submitted", { description: res.error }); return; }
    toast.success(`Complaint ${res.id} submitted`, { description: "You can follow its status under My complaints. Demo data only." });
    setV(blank); setErrors({}); onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Submit a complaint" description="Reviewed only by authorized HR staff. Your Owner and manager can't see it.">
        <div className="space-y-4 px-6 pb-6 pt-4">
          <Field label="Title" htmlFor="c-title" error={errors.title}><Input id="c-title" value={v.title} onChange={(e) => set("title", e.target.value)} aria-invalid={!!errors.title} maxLength={120} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Category" htmlFor="c-cat" error={errors.category}>
              <Select id="c-cat" value={v.category} onChange={(e) => set("category", e.target.value as ComplaintInput["category"])} aria-invalid={!!errors.category}>
                <option value="">Choose…</option>{COMPLAINT_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </Field>
            <Field label="When did it happen?" htmlFor="c-date" error={errors.incidentDate}><Input id="c-date" type="date" max={today} value={v.incidentDate} onChange={(e) => set("incidentDate", e.target.value)} aria-invalid={!!errors.incidentDate} /></Field>
          </div>
          <Field label="What happened?" htmlFor="c-desc" error={errors.description} hint="At least 30 characters. Stick to facts where you can."><Textarea id="c-desc" value={v.description} onChange={(e) => set("description", e.target.value)} aria-invalid={!!errors.description} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Concerning (optional)" htmlFor="c-who"><Select id="c-who" value={v.concerning} onChange={(e) => set("concerning", e.target.value)}><option value="">No specific person</option>{employees.filter((e) => e.id !== currentUser.id).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></Field>
            <Field label="Confidentiality" htmlFor="c-conf" error={errors.confidentiality}><Select id="c-conf" value={v.confidentiality} onChange={(e) => set("confidentiality", e.target.value as ComplaintInput["confidentiality"])}><option>Standard</option><option>Confidential</option></Select></Field>
          </div>
          <label className="flex items-center justify-between gap-3 rounded-xl bg-canvas px-4 py-3 text-[13px]">
            <span><span className="font-medium">Hide my name from reviewers</span><span className="block text-xs text-ink-3">Simulated in this demo; real anonymity depends on how the backend stores identity.</span></span>
            <Switch checked={v.anonymous} onCheckedChange={(c) => set("anonymous", c)} aria-label="Hide my name from reviewers" />
          </label>
          <div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="gradient" onClick={onSubmit}>Submit complaint</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
