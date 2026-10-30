"use client";
import * as React from "react";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { visibleAudit } from "@/lib/audit-visibility";
import { useWorkspace } from "@/stores/workspace-store";
import { useAdministration } from "@/stores/admin-store";
import { useTenant } from "@/stores/tenant-store";
import { useUI } from "@/stores/ui-store";
import { canAccess } from "@/lib/permissions";
import { useDataset } from "@/lib/api";
import { timeAgo } from "@/lib/utils/format";

const tone = { Owner: "violet", People: "mint", DevTrack: "sky", VADER: "coral", System: "violet" } as const;

export default function ActivityPage() {
  const { activity, currentUser } = useDataset();
  const role = useUI((s) => s.role);
  const complaints = useWorkspace((s) => s.complaints);
  const audit = useWorkspace((s) => s.audit);
  const org = useTenant((s) => s.orgId);
  const administration = useAdministration((s) => s.organizations[org]);
  const data = [...(administration?.audit ?? []), ...audit].filter((entry) => entry.result === "Simulated" && visibleAudit(entry, role, complaints.map((c) => c.id))).map((entry) => ({ id: entry.id, actor: entry.actor, text: `${entry.action} · ${entry.target}`, module: entry.module, at: entry.at })).concat(activity);
  const [tab, setTab] = React.useState("all");
  const list = (data ?? []).filter((a) => (a.module === "System" ? (["owner", "hr"].includes(role) || a.actor === currentUser.id || a.actor === currentUser.name) : canAccess(role, `/${a.module.toLowerCase()}`)) && !/complaint/i.test(a.text) && (tab === "all" || a.module === tab)).sort((a,b) => b.at.localeCompare(a.at));
  return (
    <div>
      <PageHeader title="Activity feed" description="What happened across every module, newest first." />
      <Tabs value={tab} onValueChange={setTab}><TabsList>{["all", "Owner", "People", "DevTrack", "VADER"].map((t) => <TabsTrigger key={t} value={t} className="capitalize">{t}</TabsTrigger>)}</TabsList></Tabs>
      <Card className="mt-4"><CardBody>
          <ul className="space-y-5">{list.map((a) => <li key={a.id} className="flex items-center gap-3"><Avatar name={a.actor} size={36} /><p className="flex-1 text-sm"><span className="font-semibold">{a.actor}</span> {a.text}</p><Badge tone={tone[a.module]}>{a.module}</Badge><span className="w-16 text-right text-xs text-ink-3">{timeAgo(a.at)}</span></li>)}</ul>
      </CardBody></Card>
    </div>
  );
}
