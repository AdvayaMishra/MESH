"use client";
import {isLive} from "@/lib/connected/live-state";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Banknote, CalendarClock, MessageSquareWarning, UserCheck, UserPlus, Users } from "lucide-react";
import { PageHeader } from "@/components/features/page-header";
import { KpiCard } from "@/components/features/kpi-card";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";
import { isOpen, visibleComplaints } from "@/lib/complaints";
import { fmtCurrency, fmtDate } from "@/lib/utils/format";
import { colors } from "@/lib/design-tokens";
import { useDataset } from "@/lib/api";

export default function PeopleOverview() {
  const { employees, payrollSummary, employeeName, currentUser } = useDataset();
  const role = useUI((st) => st.role);
  const complaints = useWorkspace((st) => st.complaints);
  const promotions = useWorkspace((st) => st.promotions);
  // Only HR reviewers get a complaint count (Owner never sees complaint data). Restricted/redacted cases are excluded.
  const openCases = role === "hr" ? visibleComplaints(complaints, { id: currentUser.id, role }).filter((x) => x.kind === "reviewer" && isOpen(x.c)).length : 0;
  const pendingPromos = promotions.filter((p) => p.status === "Pending HR review" || p.status === "Pending Owner approval").length;
  const ids = useWorkspace((s) => s.idSubmissions);
  const leave = useWorkspace((s) => s.leave);
  const pendingIds = ids.filter((i) => i.status === "Pending review").length;
  const pendingLeave = leave.filter((l) => l.status === "Pending").length;
  const joiners = employees.filter((e) => e.status === "Onboarding");
  const leaver = employees.find((e) => e.status === "Offboarding");
  const probation = employees.filter((e) => e.status === "Probation");
  const events = isLive()?[]:[
    ...(leaver ? [{ d: "2026-10-26", t: `${leaver.name}: last working day`, c: "coral" as const }] : []),
    ...(probation[0] ? [{ d: "2026-11-02", t: `${probation[0].name}: 6-month review`, c: "amber" as const }] : []),
    ...(probation.length ? [{ d: "2026-11-19", t: `Probation reviews due (${probation.length})`, c: "violet" as const }] : []),
    { d: "2026-12-01", t: "Annual salary revision window opens", c: "sky" as const },
  ];
  const deptData = [...new Set(employees.map((e) => e.department))].map((department) => ({ dept: department.slice(0, 5), headcount: employees.filter((e) => e.department === department).length }));

  return (
    <div className="space-y-6">
      <PageHeader title="MESH People" description="Hiring, verification, payroll and the full employee lifecycle." actions={<Link href="/people/lifecycle" className="inline-flex h-10 items-center gap-2 rounded-xl gradient-mint px-4 text-sm font-medium text-[#04332b]"><UserPlus className="size-4" /> Onboard employee</Link>} />
      <section aria-label="People metrics" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Total employees" value={employees.length} delta={isLive()?undefined:3} deltaLabel="joined this quarter" icon={Users} accent="mint" variant="gradient" href="/people/directory" />
        <KpiCard label="New joiners" value={joiners.length} icon={UserPlus} accent="violet" href="/people/lifecycle" />
        <KpiCard label="Pending ID verifications" value={pendingIds} icon={UserCheck} accent="amber" href="/people/verification" />
        <KpiCard label="Leave requests" value={pendingLeave} icon={CalendarClock} accent="sky" href="/people/payroll" />
        <KpiCard label="Payroll this month" value={payrollSummary.gross} format={(n) => fmtCurrency(n, true)} delta={isLive()?undefined:2.1} goodWhen="down" icon={Banknote} accent="violet" href="/people/payroll" />
        {role === "hr"
          ? <KpiCard label="Open complaints" value={openCases} icon={MessageSquareWarning} accent="coral" href="/people/complaints" />
          : <KpiCard label="Promotion proposals in review" value={pendingPromos} icon={MessageSquareWarning} accent="coral" href="/people/promotions" />}
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Headcount by department" subtitle="Includes active, onboarding and on-leave employees" />
          <CardBody>
            <div className="h-60" role="img" aria-label="Bar chart of headcount by department">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={deptData} margin={{ left: -24, right: 4, top: 8 }}>
                  <CartesianGrid vertical={false} stroke="#EEF1FA" />
                  <XAxis dataKey="dept" {...axisProps} />
                  <YAxis {...axisProps} allowDecimals={false} />
                  <Tooltip cursor={{ fill: "rgba(0,201,167,0.06)" }} content={<ChartTooltip />} />
                  <Bar dataKey="headcount" name="Headcount" fill={colors.mint} radius={[8, 8, 0, 0]} barSize={32} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Upcoming lifecycle events" />
          <CardBody>
            <ul className="space-y-3">
              {events.map((e) => (
                <li key={e.t} className="flex items-start gap-3">
                  <span className="flex w-12 shrink-0 flex-col items-center rounded-xl bg-canvas py-1.5 text-center"><span className="text-[10px] font-medium uppercase text-ink-3">{fmtDate(e.d, { month: "short" })}</span><span className="font-display text-base font-bold">{new Date(e.d).getUTCDate()}</span></span>
                  <div className="pt-1 text-[13px] text-ink">{e.t}</div>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="New joiners" subtitle="Onboarding in progress" action={<Link href="/people/verification" className="text-[13px] font-medium text-indigo hover:underline">Verification queue</Link>} />
          <CardBody>
            <ul className="divide-y divide-line">
              {joiners.map((e) => (
                <li key={e.id} className="flex items-center gap-3 py-3">
                  <Avatar name={e.name} size={36} />
                  <div className="min-w-0 flex-1"><Link href={`/people/directory/${e.id}`} className="block truncate text-sm font-medium hover:text-indigo">{e.name}</Link><p className="truncate text-xs text-ink-3">{e.role} · starts {fmtDate(e.joinDate, { month: "short", day: "numeric" })}</p></div>
                  <Badge tone={e.verification === "Verified" ? "mint" : e.verification === "Pending review" ? "amber" : "coral"} dot>{e.verification}</Badge>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Payroll summary" subtitle={payrollSummary.month} action={<SimulatedTag />} />
          <CardBody>
            <div className="grid grid-cols-3 gap-3 text-center">
              {[["Gross", payrollSummary.gross], ["Net", payrollSummary.net], ["Taxes", payrollSummary.taxes]].map(([k, v]) => (
                <div key={String(k)} className="rounded-xl bg-canvas p-3"><p className="text-xs text-ink-3">{k}</p><p className="font-display text-lg font-bold">{fmtCurrency(Number(v), true)}</p></div>
              ))}
            </div>
            <p className="mt-4 text-xs text-ink-2">Calculations use mock rules until real business logic is connected. {payrollSummary.discrepancies.length} items need review: {payrollSummary.discrepancies.map((d) => employeeName(d.employee)).join(", ")}.</p>
            <Link href="/people/payroll" className="mt-3 inline-block text-[13px] font-medium text-indigo hover:underline">Open payroll and leave</Link>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
