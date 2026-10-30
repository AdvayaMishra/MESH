"use client";
import * as React from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/input";
import { DataTable } from "@/components/ui/data-table";
import { visibleAudit } from "@/lib/audit-visibility";
import { useUI } from "@/stores/ui-store";
import { useAdministration } from "@/stores/admin-store";
import { useTenant } from "@/stores/tenant-store";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtDate, fmtTime } from "@/lib/utils/format";
import { downloadCsv } from "@/lib/export/csv";
import type { AuditEntry } from "@/lib/types";

export default function AuditPage() {
  const role = useUI((s) => s.role);
  const complaints = useWorkspace((s) => s.complaints);
  const workspaceAudit = useWorkspace((s) => s.audit);
  const org = useTenant((s) => s.orgId);
  const adminAudit = useAdministration((s) => s.organizations[org]?.audit);
  const audit = [...(adminAudit ?? []), ...workspaceAudit].filter((entry) => visibleAudit(entry, role, complaints.map((c) => c.id))).sort((a, b) => b.at.localeCompare(a.at));
  const [mod, setMod] = React.useState("all");
  const [res, setRes] = React.useState("all");
  const [search, setSearch] = React.useState("");
  const rows = audit.filter((a) => (mod === "all" || a.module === mod) && (res === "all" || a.result === res));
  const exportedRows = rows.filter((a) => JSON.stringify(a).toLowerCase().includes(search.toLowerCase()));
  const columns = React.useMemo<ColumnDef<AuditEntry, unknown>[]>(() => [
    { accessorKey: "at", header: "When", cell: ({ getValue }) => <span className="whitespace-nowrap text-ink-2">{fmtDate(String(getValue()), { month: "short", day: "numeric" })} · {fmtTime(String(getValue()))}</span> },
    { accessorKey: "actor", header: "Actor", cell: ({ getValue }) => <span className="font-medium">{String(getValue())}</span> },
    { accessorKey: "action", header: "Action" },
    { accessorKey: "target", header: "Target", cell: ({ getValue }) => <span className="font-mono text-xs">{String(getValue())}</span> },
    { accessorKey: "module", header: "Module", cell: ({ getValue }) => <Badge tone="neutral">{String(getValue())}</Badge> },
    { accessorKey: "result", header: "Result", cell: ({ getValue }) => { const v = String(getValue()); return <Badge tone={v === "Success" ? "mint" : v === "Denied" ? "coral" : "amber"} dot>{v}</Badge>; } },
    { accessorKey: "ip", header: "IP", cell: ({ getValue }) => <span className="font-mono text-xs text-ink-3">{String(getValue())}</span> },
  ], []);
  return (
    <div>
      <PageHeader title="Audit log" description="Demo audit entries recorded by supported workflows." actions={<Button variant="secondary" disabled={!exportedRows.length} onClick={() => { downloadCsv("mesh-audit-demo.csv", ["When", "Actor", "Action", "Target", "Module", "Result", "IP"], exportedRows.map((a) => [a.at, a.actor, a.action, a.target, a.module, a.result, a.ip])); toast.success("Demo audit CSV downloaded", { description: "Includes all matching records across pages." }); }}><Download /> Export</Button>} />
      <Card><DataTable data={rows} columns={columns} pageSize={10} search={search} onSearchChange={setSearch} searchPlaceholder="Search actor, action or target" filters={<>
        <Select aria-label="Module" value={mod} onChange={(e) => setMod(e.target.value)} className="!h-10 w-36"><option value="all">All modules</option>{["Owner", "People", "DevTrack", "VADER", "System"].map((m) => <option key={m}>{m}</option>)}</Select>
        <Select aria-label="Result" value={res} onChange={(e) => setRes(e.target.value)} className="!h-10 w-36"><option value="all">All results</option>{["Success", "Denied", "Simulated"].map((m) => <option key={m}>{m}</option>)}</Select></>} /></Card>
    </div>
  );
}
