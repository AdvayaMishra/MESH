"use client";
import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Check, Lightbulb } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";
import { canReviewLeave } from "@/lib/leave";
import { fmtCurrency, fmtDate } from "@/lib/utils/format";
import { colors } from "@/lib/design-tokens";
import { useDataset } from "@/lib/api";

export default function PayrollPage() {
  const { payrollSummary, employeeName, currentUser } = useDataset();
  const role = useUI((st) => st.role);
  const { leave, decideLeave } = useWorkspace();
  const { payrollRun, preparePayroll, approvePayroll, payrollReviews, reviewPayroll } = useWorkspace();
  const pending = leave.filter((l) => l.status === "Pending");
  const split = [["Gross pay", payrollSummary.gross, colors.violet], ["Taxes", payrollSummary.taxes, colors.amber], ["Benefits", payrollSummary.benefits, colors.sky], ["Net pay", payrollSummary.net, colors.mint]] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Payroll and leave" description={`${payrollSummary.month} · ${payrollSummary.headcount} employees`} badge={<SimulatedTag label="Simulated until business rules are connected" />} />
      <Card><CardHeader title="Payroll approval" subtitle="Prepared from the displayed seeded totals. Requires two independent demo reviewers; no funds move." /><CardBody className="flex flex-wrap items-center gap-3"><Badge tone={payrollRun?.status === "Approved" ? "mint" : "amber"}>{payrollRun?.status ?? "Not prepared"}</Badge>{!payrollRun && <Button variant="secondary" onClick={() => { const result = preparePayroll(); if (result.ok) toast.success("Payroll prepared for independent demo review"); else toast.error(result.error); }}>Prepare payroll run</Button>}{payrollRun?.status === "Prepared" && <Button variant="success" disabled={payrollRun.preparedBy === currentUser.id} onClick={() => { const result = approvePayroll(); if (result.ok) toast.success("Demo payroll approved; no payment sent"); else toast.error(result.error); }}>Approve payroll run</Button>}</CardBody></Card>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {split.map(([k, v, c]) => (
          <Card key={k} className="p-5"><div className="flex items-center gap-2 text-[13px] text-ink-2"><span className="size-2.5 rounded-full" style={{ background: c }} />{k}</div><p className="mt-2 font-display text-2xl font-bold">{fmtCurrency(v)}</p></Card>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card><CardHeader title="Gross payroll trend" /><CardBody>
          <div className="h-56" role="img" aria-label="Area chart of gross payroll over six months"><ResponsiveContainer width="100%" height="100%"><AreaChart data={payrollSummary.trend} margin={{ left: -4, right: 8, top: 8 }}>
            <defs><linearGradient id="pf" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors.mint} stopOpacity={0.4} /><stop offset="100%" stopColor={colors.mint} stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="month" {...axisProps} /><YAxis {...axisProps} tickFormatter={(v: number) => `$${Math.round(v / 1000)}k`} domain={["dataMin - 20000", "dataMax + 10000"]} width={54} />
            <Tooltip content={<ChartTooltip formatter={(v) => fmtCurrency(v)} />} /><Area dataKey="gross" name="Gross" stroke={colors.mint} strokeWidth={3} fill="url(#pf)" /></AreaChart></ResponsiveContainer></div>
        </CardBody></Card>
        <Card><CardHeader title="Salary breakdown by department" /><CardBody>
          <div className="h-56" role="img" aria-label="Bar chart of payroll by department"><ResponsiveContainer width="100%" height="100%"><BarChart data={payrollSummary.byDept} layout="vertical" margin={{ left: 20, right: 12 }}>
            <CartesianGrid horizontal={false} stroke="#EEF1FA" /><XAxis type="number" {...axisProps} tickFormatter={(v: number) => `$${Math.round(v / 1000)}k`} /><YAxis type="category" dataKey="dept" {...axisProps} width={90} />
            <Tooltip cursor={{ fill: "rgba(0,201,167,0.06)" }} content={<ChartTooltip formatter={(v) => fmtCurrency(v)} />} /><Bar dataKey="amount" name="Gross" fill={colors.violet} radius={[0, 8, 8, 0]} barSize={14} /></BarChart></ResponsiveContainer></div>
        </CardBody></Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="AI-assisted discrepancy review" subtitle="Suggestions are hints for the payroll owner, not decisions" action={<SimulatedTag />} />
          <CardBody className="space-y-3">
            {payrollSummary.discrepancies.map((d) => {
              const done = payrollReviews[d.id] === "Reviewed";
              return (
                <div key={d.id} className="rounded-2xl border border-line p-4">
                  <div className="flex items-center gap-2.5"><Avatar name={employeeName(d.employee)} size={28} /><span className="text-sm font-semibold">{employeeName(d.employee)}</span>{payrollReviews[d.id] && <Badge tone={done ? "mint" : "amber"} dot>{payrollReviews[d.id]}</Badge>}</div>
                  <p className="mt-2 text-[13px] text-ink">{d.issue}</p>
                  <p className="mt-1.5 flex items-start gap-1.5 text-xs text-ink-2"><Lightbulb className="mt-0.5 size-3.5 shrink-0 text-amber" />{d.suggestion}</p>
                  {!done && <div className="mt-3 flex gap-2"><Button size="sm" variant="soft" onClick={() => { const result = reviewPayroll(d.id, "Reviewed"); if (result.ok) toast.success("Marked as reviewed (simulated)"); else toast.error(result.error); }}><Check /> Mark reviewed</Button><Button size="sm" variant="ghost" onClick={() => { const result = reviewPayroll(d.id, "Flagged for Finance"); if (result.ok) toast.info("Flagged for Finance in this demo; no external message sent"); else toast.error(result.error); }}>Flag for Finance</Button></div>}
                </div>
              );
            })}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Pending leave approvals" action={<Badge tone="amber">{pending.length} pending</Badge>} />
          <CardBody>
            {pending.length === 0 ? <p className="py-6 text-center text-sm text-ink-2">All leave requests are decided.</p> : (
              <ul className="divide-y divide-line">{pending.map((l) => (
                <li key={l.id} className="flex flex-wrap items-center gap-3 py-3">
                  <Avatar name={employeeName(l.employee)} size={34} />
                  <div className="min-w-0 flex-1"><p className="text-sm font-medium">{employeeName(l.employee)}</p><p className="text-xs text-ink-3">{l.type} · {fmtDate(l.from, { month: "short", day: "numeric" })}–{fmtDate(l.to, { month: "short", day: "numeric" })} · {l.days}d</p></div>
                  {canReviewLeave(role, currentUser.id, l)
                    ? <div className="flex gap-1.5"><Button size="sm" variant="success" onClick={() => { const r = decideLeave(l.id, "Approved"); if (r.ok) toast.success("Leave approved"); else toast.error(r.error); }}>Approve</Button><Button size="sm" variant="outlineDanger" onClick={() => { const r = decideLeave(l.id, "Rejected", "Declined by HR review"); if (r.ok) toast("Leave declined"); else toast.error(r.error); }}>Decline</Button></div>
                    : <span className="text-xs text-ink-3">{l.employee === currentUser.id ? "Your own request" : "View only"}</span>}
                </li>
              ))}</ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
