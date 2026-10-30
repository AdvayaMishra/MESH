"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, Lock, ShieldCheck, Undo2, UserX } from "lucide-react";
import { toast } from "sonner";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SeverityBadge, SimulatedTag } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ChainExplorer } from "@/components/features/vader/chain-detail";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { useWorkspace } from "@/stores/workspace-store";
import { colors } from "@/lib/design-tokens";
import { fmtDate, fmtTime, timeAgo } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

interface Action { id: string; label: string; desc: string; icon: typeof Lock; drop: number; confirm: string }
const actions: Action[] = [
  { id: "revoke", label: "Revoke active sessions", desc: "Sign out all sessions for the affected identity.", icon: UserX, drop: 12, confirm: "Sessions end immediately. The reporting job may fail until it re-authenticates." },
  { id: "rotate", label: "Rotate access key", desc: "Issue a new key and disable the old one.", icon: Lock, drop: 16, confirm: "Dependent services need the new key within 15 minutes." },
  { id: "block", label: "Block external destination", desc: "Add the unapproved endpoint to the egress denylist.", icon: ShieldCheck, drop: 14, confirm: "Outbound traffic to this endpoint is dropped for everyone." },
];

export default function IncidentDetail() {
  const { employeeName, findings } = useDataset();
  const { id } = useParams<{ id: string }>();
  const { incidentNotes, addIncidentNote, incidents, incidentResponses, approveIncidentResponse, undoIncidentResponse, setIncidentStatus } = useWorkspace();
  const inc = incidents.find((i) => i.id === id);
  const applied = incidentResponses[id] ?? [];
  const [note, setNote] = React.useState("");
  const [dlg, setDlg] = React.useState<Action | null>(null);
  if (!inc) return <EmptyState title="Incident not found" description={`No incident has the ID ${id}.`} action={<Button variant="secondary" asChild><Link href="/vader/incidents">Back to incidents</Link></Button>} />;

  const active = applied.filter((a) => !a.undone);
  const dropped = active.reduce((s, a) => s + (actions.find((x) => x.id === a.actionId)?.drop ?? 0), 0);
  const after = Math.max(inc.riskBefore, inc.riskAfter - dropped);
  const related = findings.filter((f) => f.severity === "critical" && f.status !== "Fixed").slice(0, 2);
  const isChain = !!inc.chainId;

  return (
    <div className="space-y-6">
      <Link href="/vader/incidents" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 hover:text-ink"><ArrowLeft className="size-4" /> Incidents</Link>
      <Card className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-3xl"><div className="flex flex-wrap items-center gap-2"><SeverityBadge severity={inc.severity} /><Badge tone={inc.status === "Resolved" ? "mint" : inc.status === "Contained" ? "sky" : "amber"} dot>{inc.status}</Badge><span className="font-mono text-xs text-ink-3">{inc.id}</span></div>
            <h1 className="mt-2 font-display text-2xl font-bold">{inc.title}</h1><p className="mt-2 text-[15px] text-ink-2">{inc.summary}</p></div>
          <div className="flex gap-2">
            {inc.status === "Open" && <Button variant="secondary" onClick={() => { const result = setIncidentStatus(inc.id, "Investigating"); if (result.ok) toast.success("Investigation started (demo)"); else toast.error(result.error); }}>Start investigation</Button>}
            {inc.status !== "Contained" && inc.status !== "Resolved" && <Button variant="secondary" onClick={() => { const result = setIncidentStatus(inc.id, "Contained"); if (result.ok) toast.success("Marked as contained (simulated)"); else toast.error(result.error); }}>Mark contained</Button>}
            {inc.status !== "Resolved" && <Button variant="success" onClick={() => { const result = setIncidentStatus(inc.id, "Resolved", after); if (result.ok) toast.success("Incident resolved (simulated)"); else toast.error(result.error); }}><CheckCircle2 /> Resolve</Button>}
          </div>
        </div>
        <dl className="mt-5 grid gap-4 border-t border-line pt-5 sm:grid-cols-4">{[["Detected", `${fmtDate(inc.detectedAt, { month: "short", day: "numeric" })} · ${fmtTime(inc.detectedAt)} UTC`], ["Analyst", employeeName(inc.analyst)], ["Affected resources", inc.assets.join(", ")], ["Opened", timeAgo(inc.detectedAt)]].map(([k, v]) => <div key={k}><dt className="text-xs text-ink-3">{k}</dt><dd className="mt-0.5 break-words font-medium">{v}</dd></div>)}</dl>
      </Card>

      {isChain && <ChainExplorer graphHeight={360} />}

      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader title="Suggested response" subtitle="Each action needs your approval and is simulated here" action={<SimulatedTag label="No real action taken" />} />
          <CardBody className="space-y-3">
            {actions.map((a) => {
              const run = applied.find((x) => x.actionId === a.id && !x.undone);
              return (
                <div key={a.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-line p-4">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-tint-violet text-indigo"><a.icon className="size-5" /></span>
                  <div className="min-w-0 flex-1 basis-48"><p className="text-sm font-semibold">{a.label}</p><p className="text-xs text-ink-2">{a.desc} Estimated risk −{a.drop}.</p></div>
                  {run ? <><Badge tone="mint" dot>Approved (simulated)</Badge><Button size="sm" variant="ghost" onClick={() => { const result = undoIncidentResponse(inc.id, run.id); if (result.ok) toast("Action reversed in the simulation"); else toast.error(result.error); }}><Undo2 /> Undo</Button></> : <Button size="sm" variant="soft" onClick={() => setDlg(a)}>Review and approve</Button>}
                </div>
              );
            })}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Before and after risk" subtitle="Projected effect of approved actions" />
          <CardBody>
            <div className="h-48" role="img" aria-label="Bar chart of risk before, current and after response"><ResponsiveContainer width="100%" height="100%"><BarChart data={[{ n: "Before incident", v: inc.riskBefore }, { n: "Current", v: inc.riskAfter }, { n: "After response", v: after }]} margin={{ left: -22, right: 4, top: 8 }}>
              <XAxis dataKey="n" {...axisProps} tick={{ fill: "#94A3B8", fontSize: 11 }} interval={0} /><YAxis {...axisProps} domain={[0, 100]} /><Tooltip cursor={{ fill: "rgba(99,91,255,0.06)" }} content={<ChartTooltip />} />
              <Bar dataKey="v" name="Risk" radius={[8, 8, 0, 0]} barSize={44}>{[colors.mint, colors.coral, colors.violet].map((c) => <Cell key={c} fill={c} />)}</Bar></BarChart></ResponsiveContainer></div>
            <p className="mt-2 text-center text-sm text-ink-2">{inc.riskAfter} <span className="text-ink-3">→</span> <span className="font-semibold text-indigo">{after}</span> with {active.length} approved action{active.length === 1 ? "" : "s"}</p>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Correlated evidence" />
          <CardBody><ul className="space-y-2.5 text-[13px]">
            {["Identity: new ASN and country change within 4 hours", "API: 4,820 requests, 9× the baseline", "IAM: role change outside the change window", ...related.map((f) => `Code: ${f.title} (${f.repo})`)].slice(0, 6).map((e) => <li key={e} className="flex gap-2.5 rounded-xl bg-canvas px-3.5 py-2.5"><span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-violet" />{e}</li>)}
          </ul></CardBody>
        </Card>
        <Card>
          <CardHeader title="Response history" />
          <CardBody>
            <ol className="space-y-3 border-l border-line pl-5 text-[13px]">
              {[...applied].map((a) => <li key={a.id} className="relative"><span className="absolute -left-[26px] top-1 size-3 rounded-full bg-mint ring-4 ring-white" /><p><span className="font-medium">{a.actor}</span> {a.undone ? "reversed" : "approved"} “{a.actionLabel}” <span className="text-ink-3">· simulated</span></p><p className="text-xs text-ink-3">{fmtDate(a.at)} · {a.actor} · {a.note}{a.undoneAt ? ` · reversed ${fmtDate(a.undoneAt)}` : ""}</p></li>)}
              <li className="relative"><span className="absolute -left-[26px] top-1 size-3 rounded-full bg-amber ring-4 ring-white" /><p><span className="font-medium">{employeeName(inc.analyst)}</span> opened the investigation</p><p className="text-xs text-ink-3">{timeAgo(inc.detectedAt)}</p></li>
              <li className="relative"><span className="absolute -left-[26px] top-1 size-3 rounded-full bg-coral ring-4 ring-white" /><p><span className="font-medium">VADER</span> raised the incident from correlated signals</p><p className="text-xs text-ink-3">{fmtTime(inc.detectedAt)} UTC</p></li>
            </ol>
          </CardBody>
        </Card>
      </div>

      <Card><CardHeader title="Investigation notes" subtitle="Analyst observations stored in this demo organization, with author and timestamp." /><CardBody className="space-y-4">
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); const result = addIncidentNote(id, note); if (result.ok) { setNote(""); toast.success("Investigation note saved (demo)"); } else toast.error(result.error); }}><Textarea aria-label="Investigation note" value={note} onChange={(e) => setNote(e.target.value)} minLength={10} maxLength={5000} required /><Button type="submit" variant="secondary">Add investigation note</Button></form>
        <ul className="space-y-3">{(incidentNotes[id] ?? []).map((item) => <li key={item.id} className="rounded-xl border border-line p-3"><p className="text-xs text-ink-3">{item.actor} · {fmtDate(item.at)} {fmtTime(item.at)}</p><p className="mt-1 whitespace-pre-wrap text-sm">{item.text}</p></li>)}</ul>
      </CardBody></Card>
      <ConfirmDialog
        open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}
        title={dlg ? `Approve: ${dlg.label}?` : ""} description={dlg?.confirm} confirmLabel="Approve (simulated)" requireNote="Why are you approving this?"
        onConfirm={(n) => { if (!dlg) return false; const result = approveIncidentResponse(inc.id, dlg.id, dlg.label, n); if (result.ok) toast.success("Approved in the simulation"); else toast.error(result.error); return result.ok; }}
      />
    </div>
  );
}
