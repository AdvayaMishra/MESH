"use client";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Info } from "lucide-react";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SeverityBadge, SimulatedTag } from "@/components/ui/badge";
import { ChartTooltip, Legend, axisProps } from "@/components/charts/chart-kit";
import { colors } from "@/lib/design-tokens";
import { fmtDate, fmtTime } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

export default function BehaviorPage() {
  const { apiUsage, deviceTimeline, downloadAnomalies, employeeRiskDistribution, loginActivity, dbAccess } = useDataset();
  return (
    <div className="space-y-6">
      <PageHeader title="Behavioral monitoring" description="Baselines for logins, devices, APIs and data movement." badge={<SimulatedTag label="Mock telemetry" />} />
      <div className="flex gap-3 rounded-2xl border border-dashed border-violet/30 bg-tint-violet/60 p-4 text-[13.5px] text-ink-2">
        <Info className="mt-0.5 size-4 shrink-0 text-indigo" />
        <p><span className="font-semibold text-ink">An unusual pattern is a signal to investigate, not proof of malicious intent.</span> People travel, change devices and run one-off jobs. Analysts check context before drawing conclusions.</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Login activity" subtitle="Logins per hour today, with anomalous ones highlighted" action={<Legend items={[{ label: "Logins", color: colors.cyan }, { label: "Anomalous", color: colors.coral }]} />} />
          <CardBody><div className="h-60" role="img" aria-label="Bar chart of logins per hour"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={loginActivity} margin={{ left: -22, right: 4, top: 8 }}>
            <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="hour" {...axisProps} interval={3} /><YAxis {...axisProps} /><Tooltip cursor={{ fill: "rgba(103,232,249,0.1)" }} content={<ChartTooltip />} />
            <Bar dataKey="logins" name="Logins" fill={colors.cyan} radius={[4, 4, 0, 0]} barSize={10} />
            <Line type="monotone" dataKey="anomalous" name="Anomalous" stroke={colors.coral} strokeWidth={3} dot={{ r: 3, fill: colors.coral }} /></ComposedChart></ResponsiveContainer></div></CardBody>
        </Card>
        <Card>
          <CardHeader title="API usage" subtitle="Thousand requests per day against baseline" action={<Legend items={[{ label: "Requests", color: colors.violet }, { label: "Baseline", color: colors.amber }]} />} />
          <CardBody><div className="h-60" role="img" aria-label="Area chart of daily API requests versus baseline"><ResponsiveContainer width="100%" height="100%"><AreaChart data={apiUsage} margin={{ left: -22, right: 4, top: 8 }}>
            <defs><linearGradient id="apiF" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors.violet} stopOpacity={0.35} /><stop offset="100%" stopColor={colors.violet} stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="day" {...axisProps} interval={2} /><YAxis {...axisProps} /><Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="requests" name="Requests (k)" stroke={colors.violet} strokeWidth={3} fill="url(#apiF)" />
            <Line type="monotone" dataKey="baseline" name="Baseline" stroke={colors.amber} strokeDasharray="6 4" dot={false} strokeWidth={2} /></AreaChart></ResponsiveContainer></div></CardBody>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Unusual download detection" subtitle="Volume compared with each identity’s own baseline" />
          <CardBody className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-[13px]"><thead><tr className="text-xs text-ink-3">{["Identity", "Volume", "Usual", "Destination", "Level"].map((h) => <th key={h} className="pb-2 pr-4 font-medium">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{downloadAnomalies.map((d) => <tr key={d.who}><td className="py-3 pr-4 font-medium">{d.who}</td><td className="py-3 pr-4 font-semibold">{d.volume}</td><td className="py-3 pr-4 text-ink-2">{d.baseline}</td><td className="py-3 pr-4 text-ink-2">{d.dest}</td><td className="py-3"><SeverityBadge severity={d.level} /></td></tr>)}</tbody></table></CardBody>
        </Card>
        <Card>
          <CardHeader title="Employee risk distribution" subtitle="Behavioral signal score bands" />
          <CardBody><div className="h-52" role="img" aria-label="Bar chart of employees by risk band"><ResponsiveContainer width="100%" height="100%"><BarChart data={employeeRiskDistribution} margin={{ left: -24, right: 4, top: 8 }}>
            <XAxis dataKey="band" {...axisProps} /><YAxis {...axisProps} allowDecimals={false} /><Tooltip cursor={{ fill: "rgba(99,91,255,0.06)" }} content={<ChartTooltip />} />
            <Bar dataKey="count" name="People" radius={[6, 6, 0, 0]} barSize={26}>{employeeRiskDistribution.map((b) => <Cell key={b.band} fill={b.color} />)}</Bar></BarChart></ResponsiveContainer></div>
            <p className="mt-2 text-xs text-ink-3">Scores prompt a conversation or a check. They are never used to take action on their own.</p></CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Device anomaly timeline" />
          <CardBody><ol className="space-y-4 border-l border-line pl-5">{deviceTimeline.map((d, i) => (
            <li key={i} className="relative"><span className="absolute -left-[26px] top-1.5 size-3 rounded-full ring-4 ring-white" style={{ background: d.level === "high" ? colors.coral : d.level === "medium" ? colors.amber : colors.sky }} />
              <p className="text-[13px]"><span className="font-semibold">{d.who}</span> · {d.what}</p><p className="font-mono text-[11px] text-ink-3">{fmtDate(d.at, { month: "short", day: "numeric" })} {fmtTime(d.at)} UTC</p></li>
          ))}</ol></CardBody>
        </Card>
        <Card>
          <CardHeader title="Database access analysis" subtitle="Tables read by unusual identities in 24h" />
          <CardBody className="space-y-3">{dbAccess.map((r) => [r.table, r.rows, r.who, r.tone] as const).map(([t, rows, who, c]) => (
            <div key={String(t)} className="flex items-center gap-3 rounded-xl bg-canvas px-4 py-3 text-[13px]"><code className="font-mono font-semibold">{String(t)}</code><span className="flex-1 text-ink-2">{who} · {Number(rows).toLocaleString("en-US")} rows</span><Badge tone={c as "coral" | "amber" | "mint"} dot>{c === "coral" ? "Review" : c === "amber" ? "Watch" : "Expected"}</Badge></div>
          ))}</CardBody>
        </Card>
      </div>
    </div>
  );
}
