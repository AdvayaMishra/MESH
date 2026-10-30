"use client";
import { useState } from "react";
import Link from "next/link";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Cloud, Fingerprint, KeyRound, Network, Radar, ServerCog, ShieldAlert, Siren, Zap } from "lucide-react";
import { PageHeader } from "@/components/features/page-header";
import { KpiCard } from "@/components/features/kpi-card";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { SeverityBadge, SimulatedTag } from "@/components/ui/badge";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { RiskGaugeCard, RiskRadarCard } from "@/components/features/vader/widgets";
import { AttackChainGraph } from "@/components/visualizations/attack-chain-graph";
import { useWorkspace } from "@/stores/workspace-store";
import { colors } from "@/lib/design-tokens";
import { timeAgo } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

export default function VaderOverview() {
  const { attackChain, cloudPosture, riskTrend, cloudResources } = useDataset();
  const { incidents, findings } = useWorkspace();
  const chainInc = incidents.find((i) => i.chainId);
  const [selectedSignal, setSelectedSignal] = useState<string | null>(null);
  const signal = attackChain.find((node) => node.id === selectedSignal);
  const active = incidents.filter((i) => i.status !== "Resolved");
  const vulnOpen = findings.filter((f) => f.status !== "Fixed").length;

  return (
    <div className="space-y-6">
      <PageHeader title="VADER command center" description="Behavior, identity, API and cloud signals correlated into incidents you can act on." badge={<SimulatedTag label="Demo security data" />} actions={<Link href="/vader/copilot" className="inline-flex h-10 items-center gap-2 rounded-xl gradient-violet px-4 text-sm font-medium text-white"><Radar className="size-4" /> Ask the Copilot</Link>} />

      <section aria-label="Security overview" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Active incidents" value={active.length} icon={Siren} accent="coral" variant="gradient" href="/vader/incidents" delta={1} deltaLabel="new today" goodWhen="down" />
        <KpiCard label="High-risk events (24h)" value={17} icon={ShieldAlert} accent="amber" delta={6} deltaLabel="vs yesterday" goodWhen="down" />
        <KpiCard label="Identity anomalies" value={5} icon={Fingerprint} accent="violet" href="/vader/behavior" />
        <KpiCard label="API anomalies" value={3} icon={Zap} accent="sky" href="/vader/behavior" />
        <KpiCard label="Cloud misconfigurations" value={cloudResources.length} icon={Cloud} accent="sky" href="/vader/cloud" />
        <KpiCard label="Open vulnerabilities" value={vulnOpen} icon={KeyRound} accent="mint" href="/devtrack/security" />
        <KpiCard label="Monitored assets" value={cloudResources.length} icon={ServerCog} accent="violet" />
        <KpiCard label="Cloud posture" value={cloudPosture.score} suffix="/ 100" icon={Network} accent="mint" href="/vader/cloud" delta={-2} deltaLabel="points" />
      </section>

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <RiskGaugeCard />
        <Card>
          <CardHeader title="Risk trend" subtitle="Daily overall risk, last 14 days" action={<Link href="/vader/risk" className="text-[13px] font-medium text-indigo hover:underline">Risk analytics</Link>} />
          <CardBody>
            <div className="h-64" role="img" aria-label="Area chart of daily risk score"><ResponsiveContainer width="100%" height="100%"><AreaChart data={riskTrend} margin={{ left: -22, right: 8, top: 8 }}>
              <defs><linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors.violet} stopOpacity={0.4} /><stop offset="100%" stopColor={colors.cyan} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="day" {...axisProps} interval={2} /><YAxis {...axisProps} domain={[0, 80]} /><Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="score" name="Risk" stroke={colors.violet} strokeWidth={3} fill="url(#riskFill)" /></AreaChart></ResponsiveContainer></div>
          </CardBody>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <CardHeader title="Featured attack chain" subtitle={`${chainInc?.id ?? "Seeded incident"} · ${attackChain.length} signals joined into one story`} action={<><SimulatedTag label="Seeded incident" /><Link href="/vader/attack-chain" className="text-[13px] font-medium text-indigo hover:underline">Explore</Link></>} />
        <CardBody><AttackChainGraph chain={attackChain} selectedId={selectedSignal} onSelect={setSelectedSignal} replayIndex={null} height={340} />{signal && <div className="mt-3 rounded-xl border border-line p-3 text-sm"><p className="font-semibold">Selected signal</p><p>{signal.label} · {signal.source} · risk contribution {signal.risk}</p><Link className="text-indigo hover:underline" href="/vader/attack-chain">Open full chain evidence</Link></div>}</CardBody>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card>
          <CardHeader title="Needs attention" action={<Link href="/vader/incidents" className="text-[13px] font-medium text-indigo hover:underline">All incidents</Link>} />
          <CardBody>
            <ul className="divide-y divide-line">{active.slice(0, 4).map((i) => (
              <li key={i.id}><Link href={`/vader/incidents/${i.id}`} className="flex items-center gap-3 py-3 transition-colors hover:bg-canvas">
                <SeverityBadge severity={i.severity} /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{i.title}</span><span className="text-xs text-ink-3">{i.id} · {timeAgo(i.detectedAt)} · {i.status}</span></span><span className="text-sm font-semibold text-[#c21d45]">{i.riskAfter}</span>
              </Link></li>
            ))}</ul>
          </CardBody>
        </Card>
        <RiskRadarCard />
      </div>
    </div>
  );
}
