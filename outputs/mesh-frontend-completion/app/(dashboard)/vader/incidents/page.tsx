"use client";
import * as React from "react";
import Link from "next/link";
import { Search, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { downloadCsv } from "@/lib/export/csv";
import { PageHeader } from "@/components/features/page-header";
import { Card } from "@/components/ui/card";
import { Badge, SeverityBadge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/stores/workspace-store";
import { timeAgo } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

const tone = { Open: "coral", Investigating: "amber", Contained: "sky", Resolved: "mint" } as const;

export default function IncidentsPage() {
  const { employeeName } = useDataset();
  const incidents = useWorkspace((s) => s.incidents);
  const [tab, setTab] = React.useState("all");
  const [query, setQuery] = React.useState("");
  const [severity, setSeverity] = React.useState("all");
  const list = incidents.filter((i) => {
    if (tab !== "all" && (tab === "active" ? i.status === "Resolved" : i.status !== "Resolved")) return false;
    if (severity !== "all" && i.severity.toLowerCase() !== severity) return false;
    const q = query.trim().toLocaleLowerCase();
    return !q || [i.id, i.title, i.summary, ...i.assets].some((value) => value.toLocaleLowerCase().includes(q));
  });
  return (
    <div>
      <PageHeader title="Incidents" description="Investigations with correlated evidence and human-approved responses." />
      <Tabs value={tab} onValueChange={setTab}><TabsList><TabsTrigger value="all">All</TabsTrigger><TabsTrigger value="active">Active</TabsTrigger><TabsTrigger value="resolved">Resolved</TabsTrigger></TabsList></Tabs>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[210px] flex-1">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-3" />
          <Input aria-label="Search incidents" placeholder="Search incidents or assets" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <Select aria-label="Filter incident severity" className="w-40" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="all">All severities</option>
          <option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
        </Select>
        <Button variant="secondary" disabled={!list.length} onClick={() => downloadCsv("mesh-demo-incidents.csv", ["ID", "Title", "Severity", "Status", "Detected", "Assets", "Risk before", "Risk after"], list.map((i) => [i.id, i.title, i.severity, i.status, i.detectedAt, i.assets.join("; "), i.riskBefore, i.riskAfter]))}><Download /> Export filtered CSV</Button>
      </div>
      <p className="mt-2 text-xs text-ink-3" aria-live="polite">{list.length} of {incidents.length} demo incidents shown. Exported records are simulated, not live security evidence.</p>
      <Card className="mt-4 divide-y divide-line">
        {list.length === 0 && <EmptyState title="No incidents" description="Nothing matches this filter." />}
        {list.map((i) => (
          <Link key={i.id} href={`/vader/incidents/${i.id}`} className="flex flex-wrap items-center gap-4 p-4 transition-colors hover:bg-tint-violet/30">
            <SeverityBadge severity={i.severity} />
            <div className="min-w-0 flex-1 basis-64"><p className="truncate text-sm font-semibold">{i.title}</p><p className="text-xs text-ink-3">{i.id} · detected {timeAgo(i.detectedAt)} · {i.assets.length} asset{i.assets.length > 1 ? "s" : ""}</p></div>
            <span className="flex items-center gap-2 text-xs text-ink-2"><Avatar name={employeeName(i.analyst)} size={26} />{employeeName(i.analyst).split(" ")[0]}</span>
            <span className="text-sm"><span className="text-ink-3">{i.riskBefore}</span> → <span className="font-semibold text-[#c21d45]">{i.riskAfter}</span></span>
            <Badge tone={tone[i.status]} dot>{i.status}</Badge>
          </Link>
        ))}
      </Card>
    </div>
  );
}
