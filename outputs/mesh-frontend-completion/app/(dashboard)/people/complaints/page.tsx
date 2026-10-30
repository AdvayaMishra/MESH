"use client";
import * as React from "react";
import { EyeOff, LockKeyhole, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ComplaintStatusBadge, Timeline } from "@/components/features/people/complaint-ui";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";
import { RESOLUTION_OUTCOMES, isOpen, reporterLabel, transitions, visibleComplaints, visibleEvents } from "@/lib/complaints";
import { useUI } from "@/stores/ui-store";
import { fmtDate } from "@/lib/utils/format";
import type { ComplaintOutcome, ComplaintStatus } from "@/lib/types";

/** HR review queue. Access tier comes from viewKind(): Restricted cases are redacted for HR who aren't assigned. */
export default function ComplaintReview() {
  const { currentUser, employeeName } = useDataset();
  const role = useUI((s) => s.role);
  const all = useWorkspace((s) => s.complaints);
  const st = useWorkspace();
  const [filter, setFilter] = React.useState<"open" | "all">("open");
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [note, setNote] = React.useState("");
  const [outcome, setOutcome] = React.useState<ComplaintOutcome>("Resolved informally");
  const [summary, setSummary] = React.useState("");
  const [internal, setInternal] = React.useState(false);

  const rows = visibleComplaints(all, { id: currentUser.id, role }).filter(({ kind }) => kind !== "complainant"); // own filings live under "My complaints"
  const shown = rows.filter(({ c, kind }) => filter === "all" || kind === "redacted" || isOpen(c));
  const sel = rows.find((r) => r.c.id === openId);
  const act = (r: { ok: boolean; error?: string }, okMsg: string) => { if (r.ok) toast.success(okMsg); else toast.error(r.error ?? "Not allowed"); return r.ok; };

  return (
    <div>
      <PageHeader title="Complaint review" description="Cases you're authorized to review. Restricted cases are visible only to their assigned reviewer." badge={<SimulatedTag label="Demo data · no real HR system" />}
        actions={<Select aria-label="Filter cases" className="!h-10 w-40" value={filter} onChange={(e) => setFilter(e.target.value as "open" | "all")}><option value="open">Open cases</option><option value="all">All cases</option></Select>} />
      {shown.length === 0 ? <Card><CardBody><EmptyState title="No cases to review" description="New complaints you're permitted to see will appear here." /></CardBody></Card> : (
        <Card><CardBody className="divide-y divide-line !p-0">
          {shown.map(({ c, kind }) => (
            <button key={c.id} data-testid="complaint-row" disabled={kind === "redacted"} onClick={() => { setOpenId(c.id); setNote(""); setSummary(""); }}
              className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors enabled:hover:bg-canvas disabled:cursor-not-allowed">
              <div className="min-w-0 flex-1">
                {kind === "redacted" ? (
                  <><p className="flex items-center gap-1.5 text-sm font-medium text-ink-2"><LockKeyhole className="size-3.5" /> Restricted case — details hidden</p><p className="font-mono text-xs text-ink-3">{c.id} · assigned to another reviewer</p></>
                ) : (
                  <><p className="truncate text-sm font-medium">{c.title}</p><p className="text-xs text-ink-3"><span className="font-mono">{c.id}</span> · {c.category} · {reporterLabel(c, kind, employeeName)} · {fmtDate(c.createdAt, { month: "short", day: "numeric" })}</p></>
                )}
              </div>
              {kind === "reviewer" && <Badge tone={c.confidentiality === "Restricted" ? "coral" : c.confidentiality === "Confidential" ? "amber" : "neutral"}>{c.confidentiality}</Badge>}
              {kind === "reviewer" && <ComplaintStatusBadge status={c.status} />}
            </button>
          ))}
        </CardBody></Card>
      )}

      <Dialog open={!!sel && sel.kind === "reviewer"} onOpenChange={(o) => !o && setOpenId(null)}>
        {sel && sel.kind === "reviewer" && (() => {
          const c = sel.c; const next = transitions[c.status].filter((s) => s !== "Withdrawn" && s !== "Resolved");
          return (
            <DialogContent side="right" title={c.title} description={`${c.id} · ${c.category} · ${c.confidentiality}`}>
              <div className="space-y-5 px-6 pb-8 pt-4 text-[13px]">
                <div className="flex flex-wrap items-center gap-2"><ComplaintStatusBadge status={c.status} /><Badge tone={c.priority === "High" ? "coral" : c.priority === "Medium" ? "amber" : "neutral"}>{c.priority} priority</Badge>{c.anonymous && <Badge tone="violet"><EyeOff className="mr-1 size-3" />Anonymous</Badge>}</div>
                <dl className="grid grid-cols-2 gap-3 rounded-2xl bg-canvas p-4">
                  <div><dt className="text-xs text-ink-3">Reported by</dt><dd>{reporterLabel(c, "reviewer", employeeName)}</dd></div>
                  <div><dt className="text-xs text-ink-3">Concerning</dt><dd>{c.concerning ? employeeName(c.concerning) : "—"}</dd></div>
                  <div><dt className="text-xs text-ink-3">Incident date</dt><dd>{fmtDate(c.incidentDate, { month: "short", day: "numeric", year: "numeric" })}</dd></div>
                  <div><dt className="text-xs text-ink-3">Reviewer</dt><dd>{c.assignedTo ? employeeName(c.assignedTo) : "Unassigned"}</dd></div>
                </dl>
                <p className="text-ink-2">{c.description}</p>
                {c.resolution && <div className="rounded-xl bg-tint-mint px-4 py-3 text-[#006b57]"><span className="font-medium">{c.resolution.outcome}.</span> {c.resolution.summary}</div>}
                {c.status !== "Closed" && c.status !== "Withdrawn" && (
                  <div className="space-y-3 rounded-2xl border border-line p-4">
                    <p className="font-medium">Move case</p>
                    <div className="flex flex-wrap gap-2">
                      {next.map((s) => <Button key={s} size="sm" variant="secondary" onClick={() => act(st.setComplaintStatus(c.id, s as ComplaintStatus, note), `Case moved to ${s}`)}>{c.status === "Resolved" && s === "Investigating" ? "Reopen" : `Mark ${s}`}</Button>)}
                      {!c.assignedTo || c.assignedTo !== currentUser.id ? <Button size="sm" variant="soft" onClick={() => act(st.assignComplaintToMe(c.id), "Assigned to you")}>Assign to me</Button> : null}
                      {c.confidentiality !== "Restricted" && <Button size="sm" variant="outlineDanger" onClick={() => act(st.escalateComplaint(c.id), "Escalated to Restricted")}><ShieldAlert /> Restrict</Button>}
                    </div>
                    {transitions[c.status].includes("Resolved") && (
                      <div className="space-y-2 border-t border-line pt-3">
                        <p className="font-medium">Resolve</p>
                        <Select aria-label="Outcome" value={outcome} onChange={(e) => setOutcome(e.target.value as ComplaintOutcome)}>{RESOLUTION_OUTCOMES.map((o) => <option key={o}>{o}</option>)}</Select>
                        <Textarea aria-label="Resolution summary" placeholder="Summarize the outcome (20+ characters)" value={summary} onChange={(e) => setSummary(e.target.value)} />
                        <Button size="sm" variant="success" onClick={() => act(st.resolveComplaint(c.id, outcome, summary), "Case resolved")}>Resolve case</Button>
                      </div>
                    )}
                    <div className="space-y-2 border-t border-line pt-3">
                      <Input aria-label="Case note" placeholder="Note or message" value={note} onChange={(e) => setNote(e.target.value)} />
                      <div className="flex items-center gap-2">
                        <label className="flex items-center gap-1.5 text-xs text-ink-2"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note (not shown to reporter)</label>
                        <Button size="sm" className="ml-auto" onClick={() => { if (act(st.addComplaintMessage(c.id, note, internal), internal ? "Internal note added" : "Message sent to reporter")) setNote(""); }}>Add</Button>
                      </div>
                    </div>
                  </div>
                )}
                <Timeline events={visibleEvents(c, "reviewer")} name={employeeName} />
              </div>
            </DialogContent>
          );
        })()}
      </Dialog>
    </div>
  );
}
