"use client";
import * as React from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Avatar } from "@/components/ui/avatar";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";
import { useUI } from "@/stores/ui-store";
import { canDecide, canPropose, gradeOf, higherGrades, validatePromotion } from "@/lib/promotions";
import { fmtDate } from "@/lib/utils/format";
import type { Promotion } from "@/lib/types";

const tone = (s: Promotion["status"]) => (s === "Approved" ? "mint" : s === "Rejected" ? "coral" : s === "Withdrawn" || s === "Draft" ? "neutral" : "amber") as "mint" | "coral" | "neutral" | "amber";
const blank = { employeeId: "", proposedRole: "", proposedGrade: "", effectiveDate: "", justification: "" };

export default function PromotionsPage() {
  const { employees, employeeById, employeeName, currentUser } = useDataset();
  const role = useUI((s) => s.role);
  const promos = useWorkspace((s) => s.promotions);
  const create = useWorkspace((s) => s.createPromotion);
  const decide = useWorkspace((s) => s.decidePromotion);
  const withdraw = useWorkspace((s) => s.withdrawPromotion);
  const [dlg, setDlg] = React.useState(false);
  const [v, setV] = React.useState(blank);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [selId, setSelId] = React.useState<string | null>(null);
  const [note, setNote] = React.useState("");
  const today = new Date().toISOString().slice(0, 10);
  const emp = employeeById(v.employeeId);
  const sel = promos.find((p) => p.id === selId);

  const submit = () => {
    const errs = validatePromotion(v, { employee: emp, proposerId: currentUser.id, existing: promos, today });
    setErrors(errs);
    if (Object.keys(errs).length) return;
    const r = create(v);
    if (!r.ok) { toast.error("Proposal not created", { description: r.error }); return; }
    toast.success(`Proposal ${r.id} created`, { description: "It now waits for the next reviewer. Approval records a decision only; it doesn't change pay, role records or access." });
    setV(blank); setErrors({}); setDlg(false);
  };
  const act = (p: Promotion, d: "Approved" | "Rejected") => { const r = decide(p.id, d, note); if (r.ok) { toast.success(`Proposal ${d.toLowerCase()}`); setNote(""); } else toast.error(r.error); };

  return (
    <div>
      <PageHeader title="Promotion proposals" description="Propose, review and decide promotions. A proposer can't approve their own proposal, and decisions here don't change salary, role records or access." badge={<SimulatedTag label="Demo workflow" />}
        actions={canPropose(role) && <Button variant="gradient" onClick={() => setDlg(true)}><Plus /> New proposal</Button>} />
      {promos.length === 0 ? <Card><CardBody><EmptyState title="No proposals yet" description="Create the first proposal for an active employee." /></CardBody></Card> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {promos.map((p) => {
            const can = canDecide(p, role, currentUser.id);
            return (
              <Card key={p.id} data-testid="promotion-card"><CardBody className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3"><Avatar name={employeeName(p.employeeId)} size={40} /><div><p className="font-medium">{employeeName(p.employeeId)}</p><p className="text-xs text-ink-3">{p.id} · proposed by {employeeName(p.proposedBy)}</p></div></div>
                  <Badge tone={tone(p.status)} dot>{p.status}</Badge>
                </div>
                <p className="text-sm"><span className="text-ink-2">{p.currentRole} ({p.currentGrade})</span> → <span className="font-medium">{p.proposedRole} ({p.proposedGrade})</span></p>
                <p className="text-xs text-ink-3">Effective {fmtDate(p.effectiveDate, { month: "short", day: "numeric", year: "numeric" })}</p>
                <p className="text-[13px] text-ink-2">{p.justification}</p>
                <ul className="flex flex-wrap gap-2">{p.approvals.map((a) => <li key={a.step}><Badge tone={a.state === "Approved" ? "mint" : a.state === "Rejected" ? "coral" : "amber"}>{a.step}: {a.state}{a.by ? ` · ${employeeName(a.by)}` : ""}</Badge></li>)}</ul>
                {(p.status === "Pending HR review" || p.status === "Pending Owner approval") && (
                  <div className="space-y-2 border-t border-line pt-3">
                    {can.ok ? (
                      <>
                        <Input aria-label={`Decision note for ${p.id}`} placeholder="Decision note (required to reject, 10+ characters)" value={selId === p.id ? note : ""} onFocus={() => { setSelId(p.id); }} onChange={(e) => { setSelId(p.id); setNote(e.target.value); }} />
                        <div className="flex gap-2"><Button size="sm" variant="success" onClick={() => { setSelId(p.id); act(p, "Approved"); }}>Approve</Button><Button size="sm" variant="outlineDanger" onClick={() => { setSelId(p.id); act(p, "Rejected"); }}>Reject</Button></div>
                      </>
                    ) : <p className="text-xs text-ink-3">{can.reason}</p>}
                    {p.proposedBy === currentUser.id && <Button size="sm" variant="ghost" onClick={() => { const r = withdraw(p.id); if (r.ok) toast("Proposal withdrawn"); else toast.error(r.error); }}>Withdraw proposal</Button>}
                  </div>
                )}
                <details className="text-xs text-ink-3"><summary className="cursor-pointer">History ({p.events.length})</summary><ul className="mt-2 space-y-1">{[...p.events].reverse().map((e) => <li key={e.id}>{fmtDate(e.at, { month: "short", day: "numeric" })} · {employeeName(e.actor)}: {e.text}</li>)}</ul></details>
              </CardBody></Card>
            );
          })}
        </div>
      )}
      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent title="New promotion proposal" description="Only active employees can be proposed. Grade must be higher on the same ladder.">
          <div className="space-y-4 px-6 pb-6 pt-4">
            <Field label="Employee" htmlFor="p-emp" error={errors.employeeId}>
              <Select id="p-emp" value={v.employeeId} onChange={(e) => { const x = employeeById(e.target.value); setV({ ...v, employeeId: e.target.value, proposedGrade: "", proposedRole: x ? x.role : "" }); }} aria-invalid={!!errors.employeeId}>
                <option value="">Choose…</option>{employees.filter((e) => e.id !== currentUser.id && e.status === "Active").map((e) => <option key={e.id} value={e.id}>{e.name} · {e.role}</option>)}
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Proposed role" htmlFor="p-role" error={errors.proposedRole}><Input id="p-role" value={v.proposedRole} onChange={(e) => setV({ ...v, proposedRole: e.target.value })} aria-invalid={!!errors.proposedRole} /></Field>
              <Field label={`Proposed grade${emp ? ` (now ${gradeOf(emp)})` : ""}`} htmlFor="p-grade" error={errors.proposedGrade}>
                <Select id="p-grade" value={v.proposedGrade} onChange={(e) => setV({ ...v, proposedGrade: e.target.value })} aria-invalid={!!errors.proposedGrade}><option value="">Choose…</option>{emp && higherGrades(gradeOf(emp)).map((g) => <option key={g}>{g}</option>)}</Select>
              </Field>
            </div>
            <Field label="Effective date" htmlFor="p-date" error={errors.effectiveDate}><Input id="p-date" type="date" min={today} value={v.effectiveDate} onChange={(e) => setV({ ...v, effectiveDate: e.target.value })} aria-invalid={!!errors.effectiveDate} /></Field>
            <Field label="Justification" htmlFor="p-why" error={errors.justification} hint="At least 40 characters: impact, scope and evidence."><Textarea id="p-why" value={v.justification} onChange={(e) => setV({ ...v, justification: e.target.value })} aria-invalid={!!errors.justification} /></Field>
            <div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setDlg(false)}>Cancel</Button><Button variant="gradient" onClick={submit}>Create proposal</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
