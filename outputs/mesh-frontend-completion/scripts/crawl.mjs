import { chromium } from "@playwright/test";
const mode = process.argv[2] ?? "desktop";
const vp = mode === "mobile" ? { width: 390, height: 844 } : { width: 1440, height: 900 };
const routes = ["/","/login","/register","/register/verify","/register/organization","/register/website","/register/dns","/register/pending","/forgot-password","/reset-password","/invite/hr","/invite/employee","/invite/employee/id-upload","/invite/employee/pending","/invite/employee/activate",
"/owner","/owner/finance","/owner/projects","/owner/performance","/people","/people/directory","/people/directory/LR-1010","/people/verification","/people/payroll","/people/lifecycle","/people/leave",
"/devtrack","/devtrack/projects","/devtrack/projects/PRJ-01","/devtrack/board","/devtrack/pull-requests","/devtrack/security",
"/vader","/vader/risk","/vader/attack-chain","/vader/behavior","/vader/cloud","/vader/incidents","/vader/incidents/INC-3021","/vader/copilot","/vader/simulation",
"/workspace/notifications","/workspace/activity","/workspace/reports","/workspace/audit","/workspace/organization","/workspace/settings","/workspace/help",
"/people/complaints","/people/promotions"];
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: vp });
let bad = 0;
for (const r of routes) {
  const p = await ctx.newPage(); const errs = [];
  p.on("pageerror", (e) => errs.push("PAGEERR " + e.message.slice(0, 140)));
  p.on("console", (m) => { if (m.type() === "error") errs.push("CONSOLE " + m.text().slice(0, 140)); });
  const resp = await p.goto("http://localhost:3100" + r, { waitUntil: "domcontentloaded", timeout: 20000 }).catch(() => ({ status: () => "ERR" }));
  await p.waitForTimeout(600);
  const ov = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth).catch(() => -1);
  if (errs.length || ov > 0 || resp.status() !== 200) { bad++; console.log("!!", r, "status", resp.status(), "overflowPx", ov, errs.slice(0, 2).join(" | ")); }
  await p.close();
}
console.log(`[${mode}] checked ${routes.length} routes, ${bad} flagged`);
await b.close();
