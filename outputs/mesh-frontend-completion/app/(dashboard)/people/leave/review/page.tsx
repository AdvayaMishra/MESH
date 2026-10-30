"use client";

import * as React from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { useDataset } from "@/lib/api";
import { useUI } from "@/stores/ui-store";
import { useWorkspace } from "@/stores/workspace-store";
import { canReviewLeave } from "@/lib/leave";
import { fmtDate } from "@/lib/utils/format";

export default function LeaveReviewPage() {
  const role = useUI((s) => s.role);
  const { currentUser, employeeName } = useDataset();
  const leave = useWorkspace((s) => s.leave);
  const decideLeave = useWorkspace((s) => s.decideLeave);
  const [filter, setFilter] = React.useState<"Pending" | "All">("Pending");
  const [notes, setNotes] = React.useState<Record<string, string>>({});
  const records = leave.filter((l) => filter === "All" || l.status === "Pending");
  const pending = leave.filter((l) => l.status === "Pending").length;
  const authorized = role === "hr" || role === "owner";

  if (!authorized) return <div className="rounded-2xl border border-line p-8" role="alert">You do not have permission to review employee leave.</div>;

  return <div className="space-y-6">
    <PageHeader title="Leave approval inbox" description="Review employee requests. Self-approval is prohibited." badge={<SimulatedTag label="Local demo data — not connected to payroll" />} />
    <div className="flex flex-wrap items-center gap-2">
      <Button variant={filter === "Pending" ? "primary" : "soft"} onClick={() => setFilter("Pending")}>Pending ({pending})</Button>
      <Button variant={filter === "All" ? "primary" : "soft"} onClick={() => setFilter("All")}>All requests ({leave.length})</Button>
    </div>
    {records.length === 0 ? <Card><CardBody><p className="py-8 text-center text-sm text-ink-2">No requests match this filter.</p></CardBody></Card> :
      <div className="space-y-3">{records.map((request) => {
        const mayDecide = canReviewLeave(role, currentUser.id, request);
        return <Card key={request.id}><CardBody>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="font-semibold text-ink">{employeeName(request.employee)}</h2>
              <p className="mt-1 text-sm text-ink-2">{request.type} · {fmtDate(request.from, { month: "short", day: "numeric", year: "numeric" })} – {fmtDate(request.to, { month: "short", day: "numeric", year: "numeric" })} · {request.days} working days</p>
              {request.reason && <p className="mt-2 text-sm text-ink-2">Reason: {request.reason}</p>}
            </div><Badge tone={request.status === "Approved" ? "mint" : request.status === "Rejected" ? "coral" : "amber"}>{request.status}</Badge>
          </div>
          {mayDecide ? <div className="mt-4 space-y-2">
            <label htmlFor={`reason-${request.id}`} className="block text-xs font-medium text-ink-2">Decision note (required for rejection)</label>
            <textarea id={`reason-${request.id}`} rows={2} maxLength={500} value={notes[request.id] ?? ""} onChange={(e) => setNotes((prev) => ({ ...prev, [request.id]: e.target.value }))} placeholder="Add an explanation for the employee" className="w-full rounded-xl border border-line bg-white p-3 text-sm text-ink" />
            <div className="flex gap-2"><Button size="sm" variant="success" onClick={() => { const result = decideLeave(request.id, "Approved", notes[request.id]); if (result.ok) toast.success("Request approved (demo)"); else toast.error(result.error); }}>Approve</Button>
              <Button size="sm" variant="outlineDanger" onClick={() => { const result = decideLeave(request.id, "Rejected", notes[request.id]); if (result.ok) toast.success("Request declined (demo)"); else toast.error(result.error); }}>Decline</Button></div>
          </div> : request.status === "Pending" ? <p className="mt-3 text-xs text-ink-3">{request.employee === currentUser.id ? "You cannot approve your own request." : "You cannot review this request."}</p> : null}
        </CardBody></Card>;
      })}</div>}
  </div>;
}
