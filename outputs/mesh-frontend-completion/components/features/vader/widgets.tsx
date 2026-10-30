"use client";
import * as React from "react";
import { PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScoreGauge, ChartTooltip } from "@/components/charts/chart-kit";
import { Progress } from "@/components/ui/progress";
import { colors } from "@/lib/design-tokens";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { useDataset } from "@/lib/api";

export function RiskGaugeCard({ score: providedScore, delta: providedDelta }: { score?: number; delta?: number }) {
  const { riskTrend } = useDataset();
  const score = providedScore ?? riskTrend[riskTrend.length - 1]?.score;
  const delta = providedDelta ?? (score === undefined ? 0 : score - (riskTrend[0]?.score ?? score));
  if (score === undefined) return <Card><CardHeader title="Overall risk score" /><CardBody>No risk score is available for this organization.</CardBody></Card>;
  const posture = 100 - score;
  return (
    <Card className="relative overflow-hidden">
      <div className="pointer-events-none absolute -right-10 -top-10 size-40 rounded-full bg-lavender/25 blur-3xl" />
      <CardHeader title="Overall risk score" subtitle="Higher means more risk" action={<Badge tone={score >= 70 ? "coral" : score >= 40 ? "amber" : "mint"} dot>{score >= 70 ? "High" : score >= 40 ? "Elevated" : "Low"}</Badge>} />
      <CardBody className="flex flex-col items-center">
        <ScoreGauge value={score} size={240} color={score >= 70 ? colors.coral : score >= 40 ? colors.amber : colors.mint} caption="of 100" label="Risk score" />
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-ink-2"><span className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold ${delta >= 0 ? "bg-tint-coral text-[#c21d45]" : "bg-tint-mint text-[#008068]"}`}>{delta >= 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}{Math.abs(delta)}</span>over seeded window · posture {posture}</p>
      </CardBody>
    </Card>
  );
}

export function RiskRadarCard() {
  const { riskComponents } = useDataset();
  const [width, setWidth] = React.useState(0);
  const data = riskComponents.map((c) => ({ subject: c.name, score: c.score }));
  return (
    <Card>
      <CardHeader title="Risk by category" subtitle="Eight components, weighted into the overall score" />
      <CardBody>
        <div className="h-72" role="img" aria-label="Radar chart of risk by category">
          <ResponsiveContainer width="100%" height="100%" onResize={(nextWidth) => setWidth(nextWidth)}>
            <RadarChart data={data} outerRadius={width < 400 ? "46%" : "72%"}>
              <PolarGrid stroke="#E6EAF5" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: "#64748B", fontSize: width < 400 ? 11 : 12 }} />
              <Tooltip content={<ChartTooltip />} />
              <Radar dataKey="score" name="Risk" stroke={colors.violet} strokeWidth={2.5} fill={colors.violet} fillOpacity={0.22} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </CardBody>
    </Card>
  );
}

export function RiskBreakdownCard() {
  const { riskComponents } = useDataset();
  const total = riskComponents.reduce((s, c) => s + (c.score * c.weight) / 100, 0);
  return (
    <Card>
      <CardHeader title="Contribution breakdown" subtitle={`Weighted points toward the score of ${Math.round(total)}`} />
      <CardBody className="space-y-4">
        {[...riskComponents].sort((a, b) => b.score * b.weight - a.score * a.weight).map((c) => {
          const pts = ((c.score * c.weight) / 100).toFixed(1);
          return (
            <div key={c.name}>
              <div className="mb-1.5 flex items-center justify-between text-[13px]">
                <span className="font-medium text-ink">{c.name} <span className="font-normal text-ink-3">· weight {c.weight}%</span></span>
                <span className="flex items-center gap-2"><span className={`inline-flex items-center text-xs font-semibold ${c.trend >= 0 ? "text-[#c21d45]" : "text-[#008068]"}`}>{c.trend >= 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}{Math.abs(c.trend)}</span><span className="w-12 text-right font-semibold">{pts} pts</span></span>
              </div>
              <Progress value={c.score} accent={c.score >= 65 ? "coral" : c.score >= 50 ? "amber" : "violet"} label={`${c.name} risk`} />
            </div>
          );
        })}
      </CardBody>
    </Card>
  );
}
