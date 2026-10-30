"use client";
import * as React from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { ComplaintDialog, ComplaintStatusBadge, Timeline } from "@/components/features/people/complaint-ui";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";
import { transitions, visibleEvents } from "@/lib/complaints";
import { fmtDate } from "@/lib/utils/format";

/** "My complaints": every role sees ONLY cases they filed, with complainant-visible events. Owners get no extra access. */
export default function MyComplaints() {
  const { currentUser, employeeName } = useDataset();
  const all = useWorkspace((s) => s.complaints);
  const withdraw = useWorkspace((s) => s.withdrawComplaint);
  const message = useWorkspace((s) => s.addComplaintMessage);
  const [open, setOpen] = React.useState(false);
  const [msg, setMsg] = React.useState<Record<string, string>>({});
  const mine = all.filter((c) => c.submittedBy === currentUser.id);

  return (
    <div>
      <PageHeader title="My complaints" description="Submit a concern and follow its status. Only you and authorized HR reviewers can see your cases." badge={<SimulatedTag label="Demo data · no real HR system" />}
        actions={<Button variant="gradient" onClick={() => setOpen(true)}><Plus /> New complaint</Button>} />
      <ComplaintDialog open={open} onOpenChange={setOpen} />
      {mine.length === 0 ? (
        <Card><CardBody><EmptyState title="You haven't submitted any complaints" description="If something at work isn't right, you can raise it confidentially here." action={<Button variant="gradient" onClick={() => setOpen(true)}>Submit a complaint</Button>} /></CardBody></Card>
      ) : (
        <div className="space-y-4">
          {mine.map((c) => (
            <Card key={c.id} data-testid="my-complaint"><CardBody className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0"><p className="font-mono text-xs text-ink-3">{c.id} · filed {fmtDate(c.createdAt, { month: "short", day: "numeric", year: "numeric" })}</p><h2 className="font-display text-base font-semibold">{c.title}</h2><p className="mt-0.5 text-xs text-ink-2">{c.category} · {c.confidentiality}{c.anonymous ? " · hidden from reviewers" : ""}</p></div>
                <ComplaintStatusBadge status={c.status} />
              </div>
              <p className="text-[13px] text-ink-2">{c.description}</p>
              {c.resolution && <div className="rounded-xl bg-tint-mint px-4 py-3 text-[13px] text-[#006b57]"><span className="font-medium">Outcome: {c.resolution.outcome}.</span> {c.resolution.summary}</div>}
              <Timeline events={visibleEvents(c, "complainant")} name={(id) => (id === currentUser.id ? "You" : "HR")} />
              {c.status !== "Closed" && c.status !== "Withdrawn" && (
                <div className="flex flex-wrap items-center gap-2">
                  <Input aria-label={`Reply on ${c.id}`} className="!h-10 min-w-0 flex-1" placeholder="Add a message for HR" value={msg[c.id] ?? ""} onChange={(e) => setMsg((m) => ({ ...m, [c.id]: e.target.value }))} />
                  <Button size="sm" variant="secondary" onClick={() => { const r = message(c.id, msg[c.id] ?? ""); if (r.ok) { setMsg((m) => ({ ...m, [c.id]: "" })); toast.success("Message added"); } else toast.error(r.error); }}>Send</Button>
                  {transitions[c.status].includes("Withdrawn") && <Button size="sm" variant="outlineDanger" onClick={() => { const r = withdraw(c.id); if (r.ok) toast("Complaint withdrawn"); else toast.error(r.error); }}>Withdraw</Button>}
                </div>
              )}
            </CardBody></Card>
          ))}
        </div>
      )}
      <p className="mt-4 text-xs text-ink-3">{employeeName(currentUser.id)} · Reviewers see your name unless you chose to hide it. The Owner cannot open complaints.</p>
    </div>
  );
}
