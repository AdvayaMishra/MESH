import type { CsvCell } from "./csv";

/** Opens a safe, local print view. The browser's print dialog supplies Save as PDF. */
export function printReport(title: string, headers: string[], rows: CsvCell[][]) {
  const popup = window.open("", "_blank");
  if (!popup) throw new Error("Allow the report popup to print or save a PDF.");
  popup.opener = null;
  const doc = popup.document;
  doc.title = `${title} — MESH demo report`;
  const style = doc.createElement("style");
  style.textContent = 'body{font:12px Arial,sans-serif;color:#172033;margin:32px}h1{font-size:24px;color:#635bff}p{color:#64748b}table{width:100%;border-collapse:collapse}th,td{padding:9px;border:1px solid #dfe4f2;text-align:left;overflow-wrap:anywhere}th{background:#f2efff}button{background:#635bff;color:white;border:0;border-radius:8px;padding:12px;margin:16px 0}@media print{button{display:none}thead{display:table-header-group}tr{break-inside:avoid}body{margin:12mm}}';
  doc.head.appendChild(style);
  const heading = doc.createElement("h1"); heading.textContent = title; doc.body.appendChild(heading);
  const provenance = doc.createElement("p"); provenance.textContent = `Demonstration data · ${rows.length} records · Generated ${new Date().toISOString()}. Not an official financial or security report.`; doc.body.appendChild(provenance);
  const print = doc.createElement("button"); print.textContent = "Print / save PDF"; print.onclick = () => popup.print(); doc.body.appendChild(print);
  const table = doc.createElement("table"), head = doc.createElement("thead"), body = doc.createElement("tbody"), header = doc.createElement("tr");
  for (const text of headers) { const cell = doc.createElement("th"); cell.textContent = text; header.appendChild(cell); }
  head.appendChild(header); table.appendChild(head);
  for (const row of rows) { const tr = doc.createElement("tr"); for (const value of row) { const cell = doc.createElement("td"); cell.textContent = String(value ?? ""); tr.appendChild(cell); } body.appendChild(tr); }
  table.appendChild(body); doc.body.appendChild(table); popup.focus();
}
