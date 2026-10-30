"use client";
import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useWorkspace } from "@/stores/workspace-store";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";

const palette = ["bg-violet", "bg-mint", "bg-sky", "bg-coral", "bg-amber"];

export default function LeaveCalendar() {
  const { employeeName } = useDataset();
  const leave = useWorkspace((s) => s.leave);
  const [offset, setOffset] = React.useState(0);
  const base = new Date(Date.UTC(2026, 9 + offset, 1));
  const year = base.getUTCFullYear();
  const month = base.getUTCMonth();
  const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const first = base.getUTCDay();
  const cells = Array.from({ length: first + days }, (_, i) => (i < first ? null : i - first + 1));
  const title = base.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
  const on = (d: number) => {
    const t = Date.UTC(year, month, d);
    return leave.filter((l) => l.status !== "Rejected" && l.status !== "Cancelled" && t >= Date.parse(l.from) && t <= Date.parse(l.to));
  };

  return (
    <div>
      <PageHeader title="Leave calendar" description="Approved and pending leave across the organization." actions={<div className="flex items-center gap-1.5"><Button size="icon" variant="secondary" onClick={() => setOffset((o) => o - 1)} aria-label="Previous month"><ChevronLeft /></Button><span className="w-36 text-center font-display text-sm font-semibold">{title}</span><Button size="icon" variant="secondary" onClick={() => setOffset((o) => o + 1)} aria-label="Next month"><ChevronRight /></Button></div>} />
      <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
        <Card><CardBody>
          <div className="grid grid-cols-7 gap-1.5 text-center text-xs font-medium text-ink-3">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => <div key={d} className="pb-2">{d}</div>)}</div>
          <div className="grid grid-cols-7 gap-1.5">
            {cells.map((d, i) => d === null ? <div key={i} /> : (
              <div key={i} className={cn("min-h-16 rounded-xl border border-line p-1.5 text-left sm:min-h-24", on(d).length && "bg-canvas")}>
                <span className="text-xs font-medium text-ink-2">{d}</span>
                <div className="mt-1 space-y-1">
                  {on(d).slice(0, 2).map((l) => <div key={l.id} title={`${employeeName(l.employee)} · ${l.type} (${l.status})`} className={cn("truncate rounded-md px-1.5 py-0.5 text-[10px] font-medium text-white", palette[parseInt(l.id.slice(2), 10) % palette.length], l.status === "Pending" && "opacity-60")}>{employeeName(l.employee).split(" ")[0]}</div>)}
                  {on(d).length > 2 && <span className="text-[10px] text-ink-3">+{on(d).length - 2} more</span>}
                </div>
              </div>
            ))}
          </div>
        </CardBody></Card>
        <Card><CardBody>
          <h3 className="font-display text-sm font-semibold">Legend</h3>
          <ul className="mt-3 space-y-3">
            {leave.filter((l) => l.status !== "Cancelled").map((l) => <li key={l.id} className="flex items-center gap-2.5 text-[13px]"><span className={cn("size-3 shrink-0 rounded-full", palette[parseInt(l.id.slice(2), 10) % palette.length], l.status === "Pending" && "opacity-60")} /><span className="min-w-0 flex-1 truncate">{employeeName(l.employee)}</span><Badge tone={l.status === "Approved" ? "mint" : l.status === "Pending" ? "amber" : "neutral"}>{l.status}</Badge></li>)}
          </ul>
          <p className="mt-4 text-xs text-ink-3">Faded entries are pending approval.</p>
        </CardBody></Card>
      </div>
    </div>
  );
}
