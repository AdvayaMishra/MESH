"use client";
import * as React from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { FileSearch, Pause, Play } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AttackChainGraph } from "@/components/visualizations/attack-chain-graph";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { severityStyles } from "@/lib/design-tokens";
import { fmtTime } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";

export function ChainExplorer({ graphHeight = 400 }: { graphHeight?: number }) {
  const { attackChain, incidents } = useDataset();
  const chainInc = incidents.find((i) => i.chainId);
  const [sel, setSel] = React.useState<string | null>("n6");
  const [replay, setReplay] = React.useState<number | null>(null);
  const [playing, setPlaying] = React.useState(false);
  const node = attackChain.find((n) => n.id === sel) ?? attackChain[0];
  const total = attackChain.reduce((s, n) => s + n.risk, 0);

  React.useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      setReplay((r) => {
        const next = r === null ? 0 : r + 1;
        if (next >= attackChain.length) {
          setPlaying(false);
          return null;
        }
        setSel(attackChain[next].id);
        return next;
      });
    }, 1100);
    return () => clearInterval(t);
  }, [playing, attackChain]);

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <CardHeader
          title={`Attack chain · ${chainInc?.id ?? "seeded incident"}`}
          subtitle={`${attackChain.length} correlated events on one identity, ${attackChain[0]?.at.slice(11, 16)}–${attackChain[attackChain.length - 1]?.at.slice(11, 16)} UTC`}
          action={<Button size="sm" variant={playing ? "secondary" : "soft"} onClick={() => { if (playing) { setPlaying(false); setReplay(null); } else { setReplay(null); setPlaying(true); } }}>{playing ? <><Pause /> Stop</> : <><Play /> Replay</>}</Button>}
        />
        <CardBody>
          <AttackChainGraph chain={attackChain} selectedId={sel} onSelect={(id) => { setPlaying(false); setReplay(null); setSel(id); }} replayIndex={replay} height={graphHeight} />
          <ol className="sr-only">{attackChain.map((n) => <li key={n.id}>{fmtTime(n.at)} {n.label}: {n.detail}</li>)}</ol>
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Card>
          <CardHeader title={node.label} subtitle={node.detail} action={<SeverityBadge severity={node.severity} />} />
          <CardBody className="space-y-4">
            <div className="flex flex-wrap gap-2 text-xs"><Badge tone="neutral">{fmtTime(node.at)} UTC</Badge><Badge tone="violet">Source: {node.source}</Badge><Badge tone="neutral">Adds {node.risk} to risk</Badge></div>
            <div>
              <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold"><FileSearch className="size-4 text-ink-3" />Evidence</h4>
              <ul className="space-y-2">{node.evidence.map((e) => <li key={e} className="flex gap-2.5 rounded-xl bg-canvas px-3.5 py-2.5 text-[13px] text-ink"><span className="mt-1.5 size-1.5 shrink-0 rounded-full" style={{ background: severityStyles[node.severity].hex }} />{e}</li>)}</ul>
            </div>
            <p className="text-xs text-ink-3">An analyst reviews each signal before any response. Correlation shows where to look; it does not establish who or why.</p>
          </CardBody>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader title="Risk contribution" subtitle={`${total} points across the chain`} />
            <CardBody><div className="h-44" role="img" aria-label="Bar chart of risk contribution per step"><ResponsiveContainer width="100%" height="100%"><BarChart data={attackChain.map((n) => ({ name: n.label.split(" ")[0], risk: n.risk, sev: n.severity }))} margin={{ left: -24, right: 4, top: 8 }}>
              <XAxis dataKey="name" {...axisProps} tick={{ fill: "#94A3B8", fontSize: 11 }} interval={0} /><YAxis {...axisProps} /><Tooltip cursor={{ fill: "rgba(99,91,255,0.06)" }} content={<ChartTooltip />} />
              <Bar dataKey="risk" name="Risk" radius={[6, 6, 0, 0]} barSize={22}>{attackChain.map((n) => <Cell key={n.id} fill={severityStyles[n.severity].hex} />)}</Bar></BarChart></ResponsiveContainer></div></CardBody>
          </Card>
          <Card>
            <CardHeader title="Incident timeline" />
            <CardBody>
              <ol className="relative space-y-3 border-l border-line pl-5">
                {attackChain.map((n) => (
                  <li key={n.id} className="relative"><span className="absolute -left-[26px] top-1.5 size-3 rounded-full ring-4 ring-white" style={{ background: severityStyles[n.severity].hex }} />
                    <button onClick={() => { setPlaying(false); setReplay(null); setSel(n.id); }} className={cn("block w-full rounded-lg px-2 py-1 text-left transition-colors hover:bg-canvas", sel === n.id && "bg-tint-violet")}><span className="font-mono text-[11px] text-ink-3">{fmtTime(n.at)}</span><span className="ml-2 text-[13px] font-medium">{n.label}</span></button></li>
                ))}
              </ol>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
