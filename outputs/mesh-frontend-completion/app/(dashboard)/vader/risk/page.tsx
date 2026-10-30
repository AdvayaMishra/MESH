"use client";
import * as React from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { RiskBreakdownCard, RiskGaugeCard, RiskRadarCard } from "@/components/features/vader/widgets";
import { colors } from "@/lib/design-tokens";
import { fmtDate, fmtTime } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

export default function RiskPage() {
  const { riskChangeLog, riskTrend, riskComponents, incidents } = useDataset();
  const rising = [...riskComponents].filter((c) => c.trend > 0).sort((a, b) => b.trend - a.trend).slice(0, 3);
  const falling = riskComponents.filter((c) => c.trend < 0);
  const from = riskTrend[Math.max(0, riskTrend.length - 4)]?.score ?? 0;
  const to = riskTrend[riskTrend.length - 1]?.score ?? 0;
  const chainInc = incidents.find((i) => i.chainId);
  return (
    <div className="space-y-6">
      <PageHeader title="Risk analytics" description="What makes up the score, how it changed, and why." />
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <RiskGaugeCard />
        <Card>
          <CardHeader title="Risk explanation" subtitle="Plain-language summary of the last 72 hours" />
          <CardBody className="space-y-3 text-[14.5px] leading-relaxed text-ink">
            <p>The score moved from {from} to {to}{rising.length ? <> because {rising.length} area{rising.length > 1 ? "s" : ""} worsened together: {rising.map((c, k) => <React.Fragment key={c.name}>{k > 0 && (k === rising.length - 1 ? " and " : ", ")}<strong>{c.name.toLowerCase()}</strong> (+{c.trend})</React.Fragment>)}.</> : "."}{chainInc ? ` The largest single driver is incident ${chainInc.id}, where one identity shows a chain of unusual events.` : ""}</p>
            <p className="text-ink-2">{falling.length ? `${falling.map((c) => c.name).join(" and ")} improved slightly, which kept the increase from being larger. ` : ""}The score reflects signals that need review. It does not say any person did something wrong.</p>
            <div className="flex flex-wrap gap-2 pt-1">{rising.map((c) => <Badge key={c.name} tone="coral">{c.name} ▲ {c.trend}</Badge>)}{falling.map((c) => <Badge key={c.name} tone="mint">{c.name} ▼ {Math.abs(c.trend)}</Badge>)}</div>
          </CardBody>
        </Card>
      </div>
      <Card>
        <CardHeader title="Risk trend" subtitle="Overall score with alert threshold" />
        <CardBody><div className="h-64" role="img" aria-label="Area chart of risk over 14 days with threshold at 50"><ResponsiveContainer width="100%" height="100%"><AreaChart data={riskTrend} margin={{ left: -22, right: 8, top: 8 }}>
          <defs><linearGradient id="r2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors.coral} stopOpacity={0.35} /><stop offset="100%" stopColor={colors.coral} stopOpacity={0} /></linearGradient></defs>
          <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="day" {...axisProps} /><YAxis {...axisProps} domain={[0, 80]} /><Tooltip content={<ChartTooltip />} />
          <ReferenceLine y={50} stroke={colors.amber} strokeDasharray="6 4" label={{ value: "Alert threshold", fill: "#b87400", fontSize: 11, position: "insideTopLeft" }} />
          <Area type="monotone" dataKey="score" name="Risk" stroke={colors.coral} strokeWidth={3} fill="url(#r2)" /></AreaChart></ResponsiveContainer></div></CardBody>
      </Card>
      <div className="grid gap-4 xl:grid-cols-2"><RiskBreakdownCard /><RiskRadarCard /></div>
      <Card>
        <CardHeader title="Historical changes" subtitle="Every score change links to its cause" />
        <CardBody><ul className="divide-y divide-line">{riskChangeLog.map((c) => <li key={c.at} className="flex items-center gap-4 py-3 text-sm"><span className={`w-12 rounded-lg px-2 py-1 text-center text-xs font-bold ${c.delta > 0 ? "bg-tint-coral text-[#c21d45]" : "bg-tint-mint text-[#008068]"}`}>{c.delta > 0 ? `+${c.delta}` : c.delta}</span><span className="flex-1">{c.reason}</span><span className="text-xs text-ink-3">{fmtDate(c.at, { month: "short", day: "numeric" })} · {fmtTime(c.at)}</span></li>)}</ul></CardBody>
      </Card>
    </div>
  );
}
