"use client";
import * as React from "react";
import { Download, FileBarChart, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { canAccess } from "@/lib/permissions";
import { useUI } from "@/stores/ui-store";
import { useWorkspace } from "@/stores/workspace-store";
import { useDataset } from "@/lib/api";
import { downloadCsv } from "@/lib/export/csv";
import { downloadWorkbook } from "@/lib/export/workbook";
import { printReport } from "@/lib/export/print-report";
import { buildDemoReport } from "@/lib/export/reports";
import { Field, Input, Select } from "@/components/ui/input";

const reports = [
  { id: "r1", name: "Monthly cloud spend", module: "Owner", desc: "Seeded monthly actual and forecast cloud spend.", tone: "violet" as const },
  { id: "r2", name: "Headcount and lifecycle", module: "People", desc: "Current employee department, lifecycle and verification status.", tone: "mint" as const },
  { id: "r3", name: "Sprint delivery", module: "DevTrack", desc: "Velocity, completed work and carry-over.", tone: "sky" as const },
  { id: "r4", name: "Incident security summary", module: "VADER", desc: "Current incident severity, status, dates and seeded risk values.", tone: "coral" as const },
  { id: "r5", name: "Vulnerability backlog", module: "DevTrack", desc: "Open findings by repository and severity.", tone: "sky" as const },
  { id: "r6", name: "Approval decisions", module: "Owner", desc: "Project approvals with reviewer notes.", tone: "violet" as const },
];

export default function ReportsPage() {
  const log = useWorkspace((s) => s.log);
  const role = useUI((s) => s.role);
  const visibleReports = reports.filter((report) => canAccess(role, `/${report.module.toLowerCase()}`));
  const dataset = useDataset();
  const [sel, setSel] = React.useState<(typeof reports)[number] | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [format, setFormat] = React.useState("csv");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const dateLabel = sel?.id === "r1" ? null : sel?.id === "r2" ? "Employee join date" : sel?.id === "r3" ? "Task due date" : sel?.id === "r6" ? "Decision date" : "Detection date";

  function gen() {
    if (!sel || !canAccess(role, `/${sel.module.toLowerCase()}`)) { toast.error("You cannot export this report in the current demo role."); return; }
    setBusy(true);
    try {
      const { headers, rows } = buildDemoReport(sel.id, dataset, from, to);
      if (!rows.length) throw new Error("No records match the selected report and date range.");
      if (format === "xlsx") downloadWorkbook(`mesh-${sel.id}-demo.xlsx`, headers, rows);
      else if (format === "print") printReport(`${sel.name} · ${dataset.org.name}`, headers, rows);
      else downloadCsv(`mesh-${sel.id}-demo.csv`, headers, rows);
      log({ actor: dataset.currentUser.name, action: `Exported demo ${format} report`, target: sel.name, module: "System", result: "Simulated" });
      toast.success(format === "print" ? "Print view opened; choose Print / save PDF" : "Demo report downloaded", { description: `${rows.length} rows from the current demonstration organization.` });
      setSel(null);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Report export failed."); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <PageHeader title="Reports" description="Export current demonstration records to CSV, Excel or a print-ready PDF view. Not suitable for official reporting." badge={<SimulatedTag label="Demo data export" />} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {visibleReports.map((r) => (
          <Card key={r.id} hover><CardBody className="flex h-full flex-col">
            <div className="flex items-start justify-between"><span className="flex size-10 items-center justify-center rounded-xl bg-tint-violet text-indigo"><FileBarChart className="size-5" /></span><Badge tone={r.tone}>{r.module}</Badge></div>
            <h3 className="mt-4 font-display text-base font-semibold">{r.name}</h3><p className="mt-1 flex-1 text-[13px] text-ink-2">{r.desc}</p>
            <Button variant="soft" className="mt-4 w-full" onClick={() => { setFrom(""); setTo(""); setSel(r); }}><Download /> Export</Button>
          </CardBody></Card>
        ))}
      </div>
      <Dialog open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <DialogContent title={`Export ${sel?.name ?? ""}`} description="Export the active demonstration organization. No server report is generated.">
          <div className="space-y-4">
            <Field label="Export format" htmlFor="report-format"><Select id="report-format" value={format} onChange={(e) => setFormat(e.target.value)}><option value="csv">CSV</option><option value="xlsx">Excel workbook (.xlsx)</option><option value="print">Print / save PDF</option></Select></Field>
            {dateLabel ? <fieldset className="grid grid-cols-2 gap-3"><legend className="mb-2 text-sm font-medium">Filter by {dateLabel.toLowerCase()} (optional)</legend><Field label="From date" htmlFor="report-from"><Input id="report-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field><Field label="To date" htmlFor="report-to"><Input id="report-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field></fieldset> : <p className="text-xs text-ink-3">The monthly illustration has month labels without exact timestamps; its complete seeded period is exported.</p>}
            <p className="text-sm text-ink-2">Exports contain the active organization&apos;s demo records. Unknown record dates are excluded when a date filter is selected. The PDF option opens a local report view with your browser&apos;s Print / save PDF control.</p>
            <div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setSel(null)}>Cancel</Button><Button variant="gradient" onClick={gen} disabled={busy}>{busy ? <><Loader2 className="animate-spin" /> Generating…</> : "Generate"}</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
