"use client";
import { isLive } from "@/lib/connected/live-state";
import { LiveFinanceCard } from "@/lib/connected/finance";
import * as React from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ChartTooltip, Legend, axisProps } from "@/components/charts/chart-kit";
import { Skeleton } from "@/components/ui/skeleton";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { fmtCurrency } from "@/lib/utils/format";
import { colors } from "@/lib/design-tokens";

const k = (n: number) => `$${Math.round(n / 1000)}k`;

function ChartSkeleton({ h = 240 }: { h?: number }) {
  return <Skeleton className="w-full" style={{ height: h }} />;
}

export function useFinance() {
  return useApi(() => api.finance());
}

type Finance = NonNullable<ReturnType<typeof useFinance>["data"]>;

export function CloudSpendCard({ data }: { data: Finance | null }) {
  if(isLive())return <LiveFinanceCard kind="cloud"/>;
  return (
    <Card className="h-full">
      <CardHeader
        title="Cloud expenditure"
        subtitle="Actual spend and forecast, last 7 months and next 3"
        action={<Badge tone="violet">Forecast is simulated</Badge>}
      />
      <CardBody>
        {!data ? (
          <ChartSkeleton h={280} />
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-baseline gap-x-6 gap-y-1">
              <div>
                <p className="font-display text-2xl font-bold text-ink">{fmtCurrency(data.kpis.monthlyCloudSpend)}</p>
                <p className="text-xs text-ink-2">October to date</p>
              </div>
              <Legend items={[{ label: "Actual", color: colors.violet }, { label: "Forecast", color: colors.lavender }]} />
            </div>
            <div className="h-64 w-full" role="img" aria-label="Area chart of monthly cloud spend with forecast">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.monthlyCost} margin={{ left: -12, right: 8, top: 8 }}>
                  <defs>
                    <linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={colors.violet} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={colors.violet} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke="#EEF1FA" />
                  <XAxis dataKey="month" {...axisProps} />
                  <YAxis {...axisProps} tickFormatter={k} width={52} domain={["dataMin - 10000", "dataMax + 8000"]} />
                  <Tooltip content={<ChartTooltip formatter={(v) => fmtCurrency(v)} />} />
                  <Area type="monotone" dataKey="forecast" name="Forecast" stroke={colors.lavender} strokeDasharray="5 5" strokeWidth={2} fill="transparent" />
                  <Area type="monotone" dataKey="actual" name="Actual" stroke={colors.violet} strokeWidth={3} fill="url(#actualFill)" connectNulls={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}

export function ProviderSplitCard({ data }: { data: Finance | null }) {
  if(isLive())return <LiveFinanceCard kind="provider"/>;
  const total = data?.providerSplit.reduce((s, p) => s + p.value, 0) ?? 0;
  return (
    <Card className="h-full">
      <CardHeader title="Cost by provider" subtitle="AWS, Azure and GCP this month" />
      <CardBody>
        {!data ? (
          <ChartSkeleton h={220} />
        ) : (
          <div className="flex flex-col items-center gap-4">
            <div className="relative h-44 w-44" role="img" aria-label="Donut chart of cost by cloud provider">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.providerSplit} dataKey="value" nameKey="name" innerRadius={56} outerRadius={80} paddingAngle={3} cornerRadius={6} stroke="none">
                    {data.providerSplit.map((p) => (
                      <Cell key={p.name} fill={p.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTooltip formatter={(v) => fmtCurrency(v)} />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="font-display text-xl font-bold text-ink">{k(total)}</span>
                <span className="text-[11px] text-ink-3">per month</span>
              </div>
            </div>
            <ul className="w-full space-y-2">
              {data.providerSplit.map((p) => (
                <li key={p.name} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-ink-2">
                    <span className="size-2.5 rounded-[4px]" style={{ background: p.color }} />
                    {p.name}
                  </span>
                  <span className="font-medium text-ink">
                    {fmtCurrency(p.value)} <span className="font-normal text-ink-3">· {Math.round((p.value / total) * 100)}%</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export function DepartmentSpendCard({ data }: { data: Finance | null }) {
  if(isLive())return <LiveFinanceCard kind="department"/>;
  return (
    <Card className="h-full">
      <CardHeader title="Department spending" subtitle="Cloud cost against monthly budget" />
      <CardBody className="space-y-4">
        {!data
          ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)
          : [...data.departments]
              .sort((a, b) => b.cloudSpend - a.cloudSpend)
              .map((d) => {
                const pct = Math.round((d.cloudSpend / d.budget) * 100);
                return (
                  <div key={d.dept}>
                    <div className="mb-1.5 flex items-center justify-between text-[13px]">
                      <span className="font-medium text-ink">{d.dept}</span>
                      <span className="text-ink-2">
                        {fmtCurrency(d.cloudSpend)} <span className="text-ink-3">of {fmtCurrency(d.budget, true)}</span>
                      </span>
                    </div>
                    <Progress value={pct} accent={pct >= 95 ? "coral" : pct >= 85 ? "amber" : "violet"} label={`${d.dept} budget used`} />
                  </div>
                );
              })}
      </CardBody>
    </Card>
  );
}

export function UtilizationCard({ data }: { data: Finance | null }) {
  if(isLive())return <LiveFinanceCard kind="usage"/>;
  return (
    <Card className="h-full">
      <CardHeader title="Infrastructure utilization" subtitle="Used vs reserved capacity" action={<Legend items={[{ label: "Used", color: colors.mint }, { label: "Reserved", color: "#D6F5EE" }]} />} />
      <CardBody>
        {!data ? (
          <ChartSkeleton h={220} />
        ) : (
          <div className="h-56 w-full" role="img" aria-label="Bar chart of used versus reserved infrastructure capacity">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.utilization} margin={{ left: -18, right: 4, top: 8 }} barGap={-26}>
                <CartesianGrid vertical={false} stroke="#EEF1FA" />
                <XAxis dataKey="service" {...axisProps} />
                <YAxis {...axisProps} unit="%" domain={[0, 100]} />
                <Tooltip content={<ChartTooltip formatter={(v) => `${v}%`} />} cursor={{ fill: "rgba(99,91,255,0.05)" }} />
                <Bar dataKey="reserved" name="Reserved" fill="#D6F5EE" radius={[8, 8, 0, 0]} barSize={26} />
                <Bar dataKey="used" name="Used" fill={colors.mint} radius={[8, 8, 0, 0]} barSize={26} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export function BudgetForecastCard({ data }: { data: Finance | null }) {
  if(isLive())return <LiveFinanceCard kind="budget"/>;
  const budget = 135000;
  const rows = data?.monthlyCost.map((m) => ({ month: m.month, spend: m.actual ?? m.forecast, budget })) ?? [];
  const breach = rows.find((r) => r.spend > budget);
  return (
    <Card className="h-full">
      <CardHeader
        title="Budget forecast"
        subtitle="Projected monthly spend against a $135k ceiling"
        action={breach ? <Badge tone="amber" dot>Exceeds in {breach.month}</Badge> : <Badge tone="mint" dot>Within budget</Badge>}
      />
      <CardBody>
        {!data ? (
          <ChartSkeleton h={220} />
        ) : (
          <div className="h-56 w-full" role="img" aria-label="Line chart of projected spend versus budget ceiling">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={rows} margin={{ left: -12, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={colors.sky} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={colors.sky} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#EEF1FA" />
                <XAxis dataKey="month" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={k} width={52} domain={[90000, 150000]} />
                <Tooltip content={<ChartTooltip formatter={(v) => fmtCurrency(v)} />} />
                <Area dataKey="spend" name="Spend" stroke={colors.sky} strokeWidth={3} fill="url(#spendFill)" />
                <Line dataKey="budget" name="Budget" stroke={colors.coral} strokeDasharray="6 4" dot={false} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
