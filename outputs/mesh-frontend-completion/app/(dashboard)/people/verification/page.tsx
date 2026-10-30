"use client";
import * as React from "react";
import Link from "next/link";
import { AlertTriangle, Check, FileImage, X } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtDate, timeAgo } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";

const labels = { name: "Full name", dob: "Date of birth", idNumber: "ID number", expiry: "Expiry date" } as const;

export default function VerificationCenter() {
  const { employeeById } = useDataset();
  const { idSubmissions, decideId } = useWorkspace();
  const [selectedId, setSelectedId] = React.useState(idSubmissions[0]?.id);
  const [note, setNote] = React.useState("");
  const [dialog, setDialog] = React.useState<"approve" | "reject" | null>(null);
  const sel = idSubmissions.find((s) => s.id === selectedId) ?? idSubmissions[0];
  const emp = sel ? employeeById(sel.employee) : undefined;
  const pending = idSubmissions.filter((s) => s.status === "Pending review").length;

  function decide(kind: "approve" | "reject", n: string) {
    if (!sel) return;
    const result = decideId(sel.id, kind === "approve" ? "Approved" : "Needs resubmission", n);
    if (!result.ok) { toast.error(result.error); return false; }
    toast.success(kind === "approve" ? "ID approved (simulated)" : "Resubmission requested (simulated)", { description: "Decision and note saved in this demo session. No email was sent." });
    setNote("");
  }

  return (
    <div>
      <div className="mb-3 text-sm"><Link className="text-indigo hover:underline" href="/invite/employee/pending">Return to invitation preview</Link></div>
      <PageHeader title="Verification center" description="Compare submitted details with the ID. A person always makes the final decision." badge={<Badge tone="amber" dot>{pending} pending</Badge>} />
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card className="h-fit">
          <CardHeader title="Review queue" />
          <CardBody className="space-y-2 !pt-3">
            {idSubmissions.map((s) => {
              const e = employeeById(s.employee);
              return (
                <button key={s.id} onClick={() => setSelectedId(s.id)} className={cn("flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors", sel?.id === s.id ? "border-violet/40 bg-tint-violet" : "border-line hover:bg-canvas")}>
                  <Avatar name={e?.name ?? "?"} size={36} />
                  <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{e?.name}</p><p className="text-xs text-ink-3">{timeAgo(s.submittedAt)}</p></div>
                  {s.status === "Approved" ? <Badge tone="mint" dot>Approved</Badge> : <Badge tone={s.status === "Pending review" ? "amber" : "coral"}>{s.status === "Pending review" ? "Pending" : "Resubmit"}</Badge>}
                </button>
              );
            })}
          </CardBody>
        </Card>

        {sel && emp ? (
          <div className="space-y-4">
            <Card>
              <CardHeader title={`${emp.name} · ${sel.docType}`} subtitle={`Submitted ${fmtDate(sel.submittedAt)} · ${emp.role}`} action={<SimulatedTag label="Simulated OCR" />} />
              <CardBody className="grid gap-5 md:grid-cols-[1fr_1.4fr]">
                <div>
                  <p className="mb-2 text-xs font-medium text-ink-2">Submitted ID</p>
                  <div className="flex aspect-[1.6] flex-col justify-between overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-[#eef1fa] to-white p-4">
                    <div className="flex items-center justify-between"><FileImage className="size-5 text-ink-3" /><span className="text-[10px] font-medium text-ink-3">PREVIEW · REDACTED</span></div>
                    <div className="space-y-1.5"><div className="h-2 w-2/3 rounded bg-line-strong" /><div className="h-2 w-1/2 rounded bg-line" /><div className="h-2 w-3/5 rounded bg-line" /></div>
                  </div>
                  <p className="mt-2 text-[11px] text-ink-3">This demo displays a redacted sample. No uploaded image or real OCR result is retained.</p>
                </div>
                <div>
                  <p className="mb-2 text-xs font-medium text-ink-2">Field comparison</p>
                  <div className="overflow-hidden rounded-2xl border border-line text-[13px]">
                    <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 bg-canvas px-3 py-2 text-[11px] font-medium text-ink-3"><span>Field</span><span>Employee entered</span><span>Read from ID</span><span>Match</span></div>
                    {(Object.keys(labels) as (keyof typeof labels)[]).map((k) => {
                      const a = sel.submitted[k];
                      const b = sel.ocr[k];
                      const match = a.toLowerCase() === b.toLowerCase();
                      const conf = Math.round(sel.confidence[k] * 100);
                      return (
                        <div key={k} className={cn("grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-2 border-t border-line px-3 py-2.5", !match && "bg-tint-coral/60")}>
                          <span className="text-ink-2">{labels[k]}</span>
                          <span className="break-words font-medium">{a}</span>
                          <span className="break-words font-medium">{b}<span className={cn("ml-1.5 text-[10px]", conf < 80 ? "text-[#c21d45]" : "text-ink-3")}>{conf}%</span></span>
                          {match ? <Check className="size-4 text-mint" aria-label="Matches" /> : <AlertTriangle className="size-4 text-coral" aria-label="Mismatch" />}
                        </div>
                      );
                    })}
                  </div>
                  {Object.values(sel.confidence).some((c) => c < 0.8) && <p className="mt-2 flex items-start gap-1.5 text-xs text-[#a86500]"><AlertTriangle className="mt-0.5 size-3.5" />Low-confidence fields need a closer look at the original image.</p>}
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Reviewer decision" />
              <CardBody className="space-y-3">
                <label htmlFor="note" className="text-[13px] font-medium">Reviewer notes</label>
                <Textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Explain what you checked or what the employee should fix" />
                <div className="flex flex-wrap gap-2">
                  <Button variant="success" disabled={sel.status !== "Pending review"} onClick={() => setDialog("approve")}><Check /> Approve</Button>
                  <Button variant="outlineDanger" onClick={() => setDialog("reject")} disabled={sel.status !== "Pending review" || note.trim().length < 3}><X /> Request resubmission</Button>
                </div>
                {note.trim().length < 3 && <p className="text-xs text-ink-3">A note is required to request a resubmission.</p>}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Review history" />
              <CardBody>
                {sel.history.length === 0 ? <EmptyState title="No reviews yet" description="Decisions and notes will be listed here." className="!py-6" /> : (
                  <ul className="space-y-3">{sel.history.map((h, i) => (
                    <li key={i} className="text-[13px]"><p><span className="font-medium">{h.by}</span> · {h.action} <span className="text-ink-3">· {fmtDate(h.at)}</span></p><p className="text-ink-2">“{h.note}”</p></li>
                  ))}</ul>
                )}
              </CardBody>
            </Card>
          </div>
        ) : (
          <Card><EmptyState title="Queue is empty" description="New ID submissions will appear here." /></Card>
        )}
      </div>
      <ConfirmDialog
        open={!!dialog}
        onOpenChange={(o) => !o && setDialog(null)}
        title={dialog === "approve" ? `Approve ${emp?.name}'s ID?` : `Request a new upload from ${emp?.name}?`}
        description={dialog === "approve" ? "You confirm the details match the document. This records a demo decision only; no account is activated." : "The note is recorded in the demo. No email is sent."}
        confirmLabel={dialog === "approve" ? "Approve ID" : "Request resubmission"}
        tone={dialog === "approve" ? "success" : "danger"}
        onConfirm={() => dialog ? decide(dialog, note) : false}
      />
    </div>
  );
}
