"use client";
import * as React from "react";
import { useSearchParams } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bug, FileCode2, GitBranch, KeyRound, Package, ScanSearch, ShieldAlert, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SeverityBadge, SimulatedTag } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Avatar } from "@/components/ui/avatar";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ChartTooltip, Legend, axisProps } from "@/components/charts/chart-kit";
import { KpiCard } from "@/components/features/kpi-card";
import { ScanExperience } from "@/components/features/devtrack/scan-experience";
import { useUI } from "@/stores/ui-store";
import { useWorkspace } from "@/stores/workspace-store";
import { severityStyles, colors, type Severity } from "@/lib/design-tokens";
import { fmtDate, timeAgo } from "@/lib/utils/format";
import type { Finding, FindingStatus, Scanner } from "@/lib/types";
import { useDataset } from "@/lib/api";

const scannerIcon: Record<Scanner, typeof Bug> = { Semgrep: FileCode2, Bandit: Bug, Gitleaks: KeyRound, OSV: Package };
const sevOrder: Severity[] = ["critical", "high", "medium", "low"];
const sevColor: Record<string, string> = { critical: colors.coral, high: "#FF8A3D", medium: colors.amber, low: colors.sky };

function Inner() {
  const role = useUI((s) => s.role);
  const { dependencyRisk, employeeName, scanHistory, vulnTrend, employees, currentUser } = useDataset();
  const params = useSearchParams();
  const { findings, repos, setFindingStatus, assignFinding } = useWorkspace();
  const [scan, setScan] = React.useState(params.get("scan") === "1");
  const [sev, setSev] = React.useState("all");
  const [scanner, setScanner] = React.useState("all");
  const [status, setStatus] = React.useState("all");
  const [selId, setSelId] = React.useState<string | null>(null);
  const sel = findings.find((f) => f.id === selId) ?? null;

  const open = findings.filter((f) => f.status !== "Fixed");
  const count = (s: Severity) => open.filter((f) => f.severity === s).length;
  const rows = findings.filter((f) => (sev === "all" || f.severity === sev) && (scanner === "all" || f.scanner === scanner) && (status === "all" || f.status === status));
  const byRepo = repos.map((r) => ({ repo: r.name.split("-").length > 1 ? `${r.name.split("-")[0]}·${r.name.split("-")[1].slice(0, 4)}` : r.name, ...Object.fromEntries(sevOrder.map((s) => [s, findings.filter((f) => f.repo === r.name && f.severity === s && f.status !== "Fixed").length])) }));
  const sevData = sevOrder.map((s) => ({ name: severityStyles[s].label, value: count(s), color: sevColor[s] }));
  const avgHealth = Math.round(repos.reduce((s, r) => s + r.health, 0) / repos.length);

  const columns = React.useMemo<ColumnDef<Finding, unknown>[]>(() => [
    { accessorKey: "title", header: "Finding", cell: ({ row: { original: f } }) => <div className="max-w-xs"><p className="truncate font-medium text-ink">{f.title}</p><p className="truncate font-mono text-[11px] text-ink-3">{f.file}:{f.line}</p></div> },
    { accessorKey: "severity", header: "Severity", sortingFn: (a, b) => sevOrder.indexOf(a.original.severity) - sevOrder.indexOf(b.original.severity), cell: ({ row }) => <SeverityBadge severity={row.original.severity} /> },
    { accessorKey: "scanner", header: "Scanner", cell: ({ row }) => { const I = scannerIcon[row.original.scanner]; return <span className="flex items-center gap-1.5 text-ink-2"><I className="size-3.5" />{row.original.scanner}</span>; } },
    { accessorKey: "repo", header: "Repository", cell: ({ getValue }) => <span className="font-mono text-xs">{String(getValue())}</span> },
    { accessorKey: "status", header: "Status", cell: ({ row }) => <Badge tone={row.original.status === "Fixed" ? "mint" : row.original.status === "In progress" ? "sky" : row.original.status === "Accepted risk" ? "neutral" : "amber"} dot>{row.original.status}</Badge> },
    { accessorKey: "assignee", header: "Assignee", cell: ({ row }) => <span className="flex items-center gap-2"><Avatar name={employeeName(row.original.assignee)} size={24} />{employeeName(row.original.assignee).split(" ")[0]}</span> },
  ], [employeeName]);

  return (
    <div className="space-y-6">
      <PageHeader title="Code security" description="Findings from Semgrep, Bandit, Gitleaks and OSV across authorized repositories." badge={<SimulatedTag label="Mock scan results" />} actions={<Button variant="gradient" onClick={() => setScan(true)}><ScanSearch /> Run scan</Button>} />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Severity summary">
        <KpiCard label="Critical" value={count("critical")} icon={ShieldAlert} accent="coral" variant="gradient" delta={-1} deltaLabel="vs last week" goodWhen="down" />
        <KpiCard label="High" value={count("high")} icon={Bug} accent="amber" delta={-2} deltaLabel="vs last week" goodWhen="down" />
        <KpiCard label="Medium / low" value={count("medium") + count("low")} icon={FileCode2} accent="sky" />
        <KpiCard label="Avg repository health" value={avgHealth} suffix="/ 100" icon={ShieldCheck} accent="mint" delta={3} deltaLabel="points" />
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Open by severity" />
          <CardBody>
            <div className="relative mx-auto h-48 w-48" role="img" aria-label="Donut chart of open findings by severity">
              <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={sevData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={84} paddingAngle={3} cornerRadius={6} stroke="none">{sevData.map((d) => <Cell key={d.name} fill={d.color} />)}</Pie><Tooltip content={<ChartTooltip />} /></PieChart></ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"><span className="font-display text-3xl font-bold">{open.length}</span><span className="text-[11px] text-ink-3">open</span></div>
            </div>
            <Legend className="mt-3 justify-center" items={sevData.map((d) => ({ label: d.name, color: d.color, value: String(d.value) }))} />
          </CardBody>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title="Findings by repository" subtitle="Open findings, stacked by severity" />
          <CardBody>
            <div className="h-56" role="img" aria-label="Stacked bar chart of findings by repository"><ResponsiveContainer width="100%" height="100%"><BarChart data={byRepo} margin={{ left: -22, right: 4, top: 8 }}>
              <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="repo" {...axisProps} interval={0} tick={{ fill: "#94A3B8", fontSize: 11 }} /><YAxis {...axisProps} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(56,189,248,0.07)" }} content={<ChartTooltip />} />
              {sevOrder.map((s, i) => <Bar key={s} dataKey={s} name={severityStyles[s].label} stackId="a" fill={sevColor[s]} radius={i === sevOrder.length - 1 ? [6, 6, 0, 0] : 0} barSize={30} />)}</BarChart></ResponsiveContainer></div>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Security trend" subtitle="Open findings per week" action={<Legend items={sevOrder.map((s) => ({ label: severityStyles[s].label, color: sevColor[s] }))} />} />
          <CardBody><div className="h-56" role="img" aria-label="Stacked area chart of weekly findings"><ResponsiveContainer width="100%" height="100%"><AreaChart data={vulnTrend} margin={{ left: -22, right: 4, top: 8 }}>
            <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="week" {...axisProps} /><YAxis {...axisProps} /><Tooltip content={<ChartTooltip />} />
            {[...sevOrder].reverse().map((s) => <Area key={s} type="monotone" dataKey={s} name={severityStyles[s].label} stackId="1" stroke={sevColor[s]} fill={sevColor[s]} fillOpacity={0.35} />)}</AreaChart></ResponsiveContainer></div></CardBody>
        </Card>
        <Card>
          <CardHeader title="Dependency risk" subtitle="OSV advisories across 373 packages" />
          <CardBody className="space-y-3">
            {dependencyRisk.map((d) => <div key={d.name}><div className="mb-1.5 flex justify-between text-[13px]"><span className="flex items-center gap-2"><span className="size-2.5 rounded-full" style={{ background: d.color }} />{d.name}</span><span className="font-semibold">{d.value}</span></div><Progress value={(d.value / 373) * 100} accent={d.name === "Healthy" ? "mint" : d.name === "Outdated" ? "amber" : "coral"} label={d.name} /></div>)}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Repository quality" subtitle="Health combines findings, test coverage and dependency age" />
        <CardBody className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {repos.map((r) => (
            <div key={r.name} className="rounded-2xl border border-line p-4">
              <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate font-mono text-[13px] font-semibold">{r.name}</p><p className="text-xs text-ink-3">{r.language} · scanned {timeAgo(r.lastScan)}</p></div>{r.authorized ? <Badge tone="mint" dot>Authorized</Badge> : <Badge tone="coral" dot>Revoked</Badge>}</div>
              <div className="mt-3 space-y-2"><div><div className="mb-1 flex justify-between text-xs text-ink-2"><span>Health</span><span className="font-semibold text-ink">{r.health}</span></div><Progress value={r.health} accent={r.health >= 85 ? "mint" : r.health >= 70 ? "amber" : "coral"} label="Health" /></div><div><div className="mb-1 flex justify-between text-xs text-ink-2"><span>Coverage</span><span className="font-semibold text-ink">{r.coverage}%</span></div><Progress value={r.coverage} accent="sky" label="Coverage" /></div></div>
            </div>
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Findings" subtitle="Click a row for evidence, remediation and status" className="pb-4" />
        <DataTable
          data={rows} columns={columns} pageSize={7} searchPlaceholder="Search findings, files or repositories"
          onRowClick={(f) => setSelId(f.id)}
          filters={<>
            <Select aria-label="Severity" value={sev} onChange={(e) => setSev(e.target.value)} className="!h-10 w-36"><option value="all">All severities</option>{sevOrder.map((s) => <option key={s} value={s}>{severityStyles[s].label}</option>)}</Select>
            <Select aria-label="Scanner" value={scanner} onChange={(e) => setScanner(e.target.value)} className="!h-10 w-36"><option value="all">All scanners</option>{["Semgrep", "Bandit", "Gitleaks", "OSV"].map((s) => <option key={s}>{s}</option>)}</Select>
            <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="!h-10 w-36"><option value="all">All statuses</option>{["Open", "In progress", "Fixed", "Accepted risk"].map((s) => <option key={s}>{s}</option>)}</Select>
          </>}
        />
      </Card>

      <Card>
        <CardHeader title="Scan history" />
        <CardBody className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[13px]"><thead><tr className="text-xs text-ink-3">{["Scan", "Repository", "When", "Duration", "Scanners", "Findings", "Result"].map((h) => <th key={h} className="pb-2 pr-4 font-medium">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{scanHistory.map((s) => <tr key={s.id}><td className="py-2.5 pr-4 font-mono text-xs text-ink-3">{s.id}</td><td className="py-2.5 pr-4 font-medium">{s.repo}</td><td className="py-2.5 pr-4 text-ink-2">{timeAgo(s.at)}</td><td className="py-2.5 pr-4 text-ink-2">{s.duration}</td><td className="py-2.5 pr-4"><span className="flex flex-wrap gap-1">{s.scanners.map((x) => <Badge key={x} tone="neutral" className="!text-[10px]">{x}</Badge>)}</span></td><td className="py-2.5 pr-4 font-semibold">{s.findings}</td><td className="py-2.5"><Badge tone={s.status.startsWith("Completed") ? "mint" : "coral"} dot>{s.status}</Badge></td></tr>)}</tbody></table>
        </CardBody>
      </Card>

      <Dialog open={!!sel} onOpenChange={(o) => !o && setSelId(null)}>
        {sel && (
          <DialogContent side="right" title={sel.title} description={`${sel.id} · ${sel.scanner}${sel.cwe ? ` · ${sel.cwe}` : ""}`}>
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2"><SeverityBadge severity={sel.severity} /><Badge tone="neutral">{sel.scanner}</Badge><Badge tone="neutral">Detected {fmtDate(sel.detectedAt, { month: "short", day: "numeric" })}</Badge></div>
              <div className="rounded-xl bg-canvas p-3.5 text-sm"><p className="flex items-center gap-2 font-mono text-xs"><GitBranch className="size-3.5 text-ink-3" />{sel.repo}</p><p className="mt-1 font-mono text-xs text-ink-2">{sel.file}:{sel.line}</p></div>
              <div><h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">Sanitized evidence <Badge tone="mint">Secrets redacted</Badge></h4><pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-xl bg-[#172033] p-4 font-mono text-xs leading-relaxed text-[#cfe3ff]">{sel.evidence}</pre></div>
              <div><h4 className="mb-2 text-sm font-semibold">Remediation</h4><p className="text-sm leading-relaxed text-ink-2">{sel.remediation}</p></div>
              <div className="grid grid-cols-2 gap-3">
                <label className="space-y-1.5 text-xs font-medium text-ink-3">Status<Select disabled={role === "junior-dev" && sel.assignee !== currentUser.id} value={sel.status} onChange={(e) => { const result = setFindingStatus(sel.id, e.target.value as FindingStatus); if (result.ok) toast.success(`Marked ${e.target.value.toLowerCase()} (simulated)`); else toast.error(result.error); }} className="!h-10">{["Open", "In progress", "Fixed", "Accepted risk"].map((s) => <option key={s} disabled={s === "Accepted risk" && role === "junior-dev"}>{s}</option>)}</Select></label>
                <label className="space-y-1.5 text-xs font-medium text-ink-3">Assigned to<Select value={sel.assignee} onChange={(e) => { const result = assignFinding(sel.id, e.target.value); if (result.ok) toast.success(`Assigned to ${employeeName(e.target.value)} (simulated)`); else toast.error(result.error); }} className="!h-10">{employees.filter((e) => ["senior-dev", "junior-dev", "security-analyst"].includes(e.appRole)).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></label>
              </div>
            </div>
          </DialogContent>
        )}
      </Dialog>
      <ScanExperience open={scan} onOpenChange={setScan} />
    </div>
  );
}

export default function SecurityPage() { return <React.Suspense fallback={null}><Inner /></React.Suspense>; }
