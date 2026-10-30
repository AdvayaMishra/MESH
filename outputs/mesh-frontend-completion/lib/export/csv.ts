/** Safe spreadsheet-compatible CSV export for non-sensitive demonstration records. */
export type CsvCell = string | number | boolean | null | undefined;
export function csvCell(value: CsvCell): string {
  const raw = value == null ? "" : String(value);
  // Prevent spreadsheet formula execution when exported data is opened in Excel/Sheets.
  const safe = /^[\s\u0000-\u001f]*[=+@-]/.test(raw) && typeof value !== "number" ? `'${raw}` : raw;
  return `"${safe.replace(/"/g, '""')}"`;
}
export function csvText(headers: string[], rows: CsvCell[][]): string {
  return `\uFEFF${[headers, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n")}\r\n`;
}
export function downloadCsv(filename: string, headers: string[], rows: CsvCell[][]) {
  const blob = new Blob([csvText(headers, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.replace(/[^a-zA-Z0-9._-]/g, "_");
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
