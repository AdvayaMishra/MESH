import type { Dataset } from "@/lib/api/dataset";
import type { CsvCell } from "./csv";
export interface DemoReport { headers: string[]; rows: CsvCell[][]; dateLabel: string | null; excludedUnknownDates: number }
export function buildDemoReport(id: string, d: Dataset, from = "", to = ""): DemoReport {
  const validDay = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
  if ((from && !validDay(from)) || (to && !validDay(to)) || (from && to && from > to)) throw new Error("Choose a valid date range in order.");
  let headers: string[], records: { date?: string; values: CsvCell[] }[], dateLabel: string | null;
  switch (id) {
    case "r1": headers = ["Month", "Actual spend (USD)", "Forecast spend (USD)"]; dateLabel = null; records = d.monthlyCost.map((r) => ({ values: [r.month, r.actual, r.forecast] })); break;
    case "r2": headers = ["Employee ID", "Employee", "Department", "Lifecycle status", "Verification", "Joined"]; dateLabel = "Employee join date"; records = d.employees.map((r) => ({ date: r.joinDate, values: [r.id, r.name, r.department, r.status, r.verification, r.joinDate] })); break;
    case "r3": headers = ["Task", "Project", "Sprint", "Status", "Points", "Assignee", "Due date"]; dateLabel = "Task due date"; records = d.tasks.map((r) => ({ date: r.due, values: [r.title, d.projectById(r.projectId)?.name ?? r.projectId, r.sprint, r.status, r.points, d.employeeName(r.assignee), r.due] })); break;
    case "r4": headers = ["Incident", "Severity", "Status", "Detected", "Risk before", "Risk after"]; dateLabel = "Detection date"; records = d.incidents.map((r) => ({ date: r.detectedAt, values: [r.title, r.severity, r.status, r.detectedAt, r.riskBefore, r.riskAfter] })); break;
    case "r5": headers = ["Finding", "Severity", "Scanner", "Repository", "Status", "Detected"]; dateLabel = "Detection date"; records = d.findings.filter((r) => r.status !== "Fixed").map((r) => ({ date: r.detectedAt, values: [r.title, r.severity, r.scanner, r.repo, r.status, r.detectedAt] })); break;
    case "r6": headers = ["Project", "Decision", "Reviewer", "Note", "When"]; dateLabel = "Decision date"; records = Object.entries(d.approvalHistory).flatMap(([projectId, history]) => history.map((r) => ({ date: r.at, values: [d.projectById(projectId)?.name ?? projectId, r.action, r.by, r.note, r.at] }))); break;
    default: throw new Error("Unknown report.");
  }
  let excludedUnknownDates = 0;
  const rows = records.filter((r) => {
    if (!dateLabel || (!from && !to)) return true;
    if (!r.date || Number.isNaN(Date.parse(r.date))) { excludedUnknownDates++; return false; }
    const day = r.date.slice(0, 10);
    return (!from || day >= from) && (!to || day <= to);
  }).map((r) => r.values);
  return { headers, rows, dateLabel, excludedUnknownDates };
}
