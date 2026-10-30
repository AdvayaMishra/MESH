"use client";
import * as React from "react";
import { Cloud, Database, Globe, HardDrive, KeyRound, Lightbulb, Server } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { SeverityBadge, SimulatedTag } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { ScoreGauge } from "@/components/charts/chart-kit";
import { Progress } from "@/components/ui/progress";
import { severityStyles, colors } from "@/lib/design-tokens";
import { IntegrationDraft } from "@/components/features/integration-draft";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";

const provColor = { AWS: colors.violet, Azure: colors.sky, GCP: colors.mint } as const;
const fixes: Record<string, string> = {
  "R-901": "Block public access on the bucket and serve artifacts through signed URLs.",
  "R-902": "Replace AdministratorAccess with a scoped deploy policy and link a change request.",
  "R-903": "Enable a customer-managed KMS key and rotate on the next maintenance window.",
  "R-904": "Restrict the firewall to the app subnet and the VPN range.",
  "R-906": "Close SSH to the internet and use the IAP tunnel for node access.",
  "R-907": "Rotate the key, enforce MFA, and replace wildcard access with named buckets.",
};

export default function CloudPage() {
  const { cloudPosture, cloudResources, employeeName } = useDataset();
  const [ticket, setTicket] = React.useState<string | null>(null);
  const [prov, setProv] = React.useState("all");
  const { cloudRemediations, remediateCloud } = useWorkspace();
  const done = Object.keys(cloudRemediations);
  const list = cloudResources.filter((r) => prov === "all" || r.provider === prov);
  const groups = [
    { icon: HardDrive, label: "Public storage", n: cloudResources.filter((r) => r.type.includes("S3")).length },
    { icon: KeyRound, label: "IAM permission risks", n: cloudResources.filter((r) => r.type.startsWith("IAM")).length },
    { icon: Database, label: "Database configuration", n: cloudResources.filter((r) => /SQL|RDS/.test(r.type)).length },
    { icon: Globe, label: "Network exposure", n: cloudResources.filter((r) => /firewall|SSH|internet/i.test(r.issue)).length },
  ];
  const recs = list.filter((r) => !done.includes(r.id)).slice(0, 4);

  return (
    <div className="space-y-6">
      <PageHeader title="Cloud security" description="Inventory, exposure and permission risks across AWS, Azure and GCP." badge={<SimulatedTag label="Mock inventory" />} actions={<Select aria-label="Provider" value={prov} onChange={(e) => setProv(e.target.value)} className="!h-10 w-40"><option value="all">All providers</option><option>AWS</option><option>Azure</option><option>GCP</option></Select>} />
      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
        <Card><CardHeader title="Cloud posture score" /><CardBody className="flex flex-col items-center"><ScoreGauge value={cloudPosture.score} size={220} caption="of 100" label="Cloud posture" />
          <div className="mt-5 w-full space-y-3">{cloudPosture.byProvider.map((p) => <div key={p.name}><div className="mb-1 flex justify-between text-[13px]"><span className="flex items-center gap-2"><span className="size-2.5 rounded-full" style={{ background: provColor[p.name as keyof typeof provColor] }} />{p.name}</span><span className="font-semibold">{p.score}</span></div><Progress value={p.score} accent={p.score >= 80 ? "mint" : "amber"} label={p.name} /></div>)}</div></CardBody></Card>
        <div className="grid gap-4 sm:grid-cols-2">{groups.map((g) => <Card key={g.label} className="flex items-center gap-4 p-5"><span className="flex size-12 items-center justify-center rounded-2xl bg-tint-sky text-[#0b78b0]"><g.icon className="size-6" /></span><div><p className="font-display text-3xl font-bold">{g.n}</p><p className="text-[13px] text-ink-2">{g.label}</p></div></Card>)}</div>
      </div>
      <Card>
        <CardHeader title="Resource inventory" subtitle={`${list.length} resources with open findings`} />
        <CardBody className="overflow-x-auto"><table className="w-full min-w-[820px] text-left text-[13px]"><thead><tr className="text-xs text-ink-3">{["Resource", "Provider", "Type", "Region", "Risk", "Issue", "Owner"].map((h) => <th key={h} className="pb-2 pr-4 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line">{list.map((r) => <tr key={r.id} className={done.includes(r.id) ? "opacity-50" : ""}><td className="py-3 pr-4"><span className="flex items-center gap-2 font-mono text-xs font-semibold"><Server className="size-3.5 text-ink-3" />{r.name}</span></td><td className="py-3 pr-4"><span className="flex items-center gap-1.5"><Cloud className="size-3.5" style={{ color: provColor[r.provider] }} />{r.provider}</span></td><td className="py-3 pr-4 text-ink-2">{r.type}</td><td className="py-3 pr-4 text-ink-2">{r.region}</td><td className="py-3 pr-4"><SeverityBadge severity={done.includes(r.id) ? "info" : r.risk} /></td><td className="py-3 pr-4 text-ink">{r.issue}</td><td className="py-3 text-ink-2">{employeeName(r.owner).split(" ")[0]}</td></tr>)}</tbody></table></CardBody>
      </Card>
      <Card>
        <CardHeader title="Remediation recommendations" subtitle="Suggested steps. Nothing changes in your cloud from here." action={<SimulatedTag />} />
        <CardBody className="grid gap-3 md:grid-cols-2">
          {done.map((id) => { const resource = cloudResources.find((v) => v.id === id); if (!resource || (prov !== "all" && resource.provider !== prov)) return null; return <div key={id} className="rounded-xl border border-line p-3 text-sm">{resource.name} · simulated remediation recorded <Button size="sm" variant="ghost" onClick={() => { const result = remediateCloud(id, true); if (!result.ok) toast.error(result.error); }}>Reopen</Button></div>; })}
          {recs.length === 0 && <p className="col-span-2 py-6 text-center text-sm text-ink-2">All recommendations for this view are marked done.</p>}
          {recs.map((r) => <div key={r.id} className="rounded-2xl border border-line p-4"><div className="flex items-center justify-between gap-2"><p className="font-mono text-[13px] font-semibold">{r.name}</p><span className={`size-2.5 rounded-full ${severityStyles[r.risk].dot}`} /></div><p className="mt-2 flex gap-2 text-[13px] text-ink-2"><Lightbulb className="mt-0.5 size-4 shrink-0 text-amber" />{fixes[r.id] ?? `Review ${r.issue.toLowerCase()} against your organization policy; validate a scoped change with the resource owner.`}</p><div className="mt-3 flex gap-2"><Button size="sm" variant="soft" onClick={() => { const result = remediateCloud(r.id); if (result.ok) toast.success("Marked as remediated (simulated)", { description: `${r.name} · verify in your cloud console` }); else toast.error(result.error); }}>Mark remediated</Button><Button size="sm" variant="ghost" onClick={() => setTicket(r.name)}>Create ticket draft</Button></div></div>)}
        </CardBody>
      </Card>
      <IntegrationDraft open={!!ticket} onOpenChange={(open) => !open && setTicket(null)} target={ticket ?? ""} title="Cloud remediation ticket draft" />
    </div>
  );
}
