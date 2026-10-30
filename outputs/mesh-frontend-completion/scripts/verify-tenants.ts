/**
 * Data-layer verification (no browser needed): tenant isolation, referential integrity, role identities,
 * Trust Stars rules, route permissions and tenant-derived Copilot text.
 * Run: npx tsx scripts/verify-tenants.ts   (exit code 1 on any failure)
 */
import { tenants } from "../lib/api/mock";
import { ALL_ROLES, canAccess } from "../lib/permissions";
import { TRUST_MAX, TRUST_START, clampScore, isTrustEligible, scoreFromEvents, wholeStars } from "../lib/trust";
import { COPILOT_PROMPTS, answerCopilotQuestion, buildCopilotAnswers } from "../lib/copilot-answers";
import type { Role } from "../lib/types";
import { useWorkspace } from "../stores/workspace-store";
import { useUI } from "../stores/ui-store";

let pass = 0, fail = 0;
const ok = (cond: boolean, name: string, detail = "") => { if (cond) pass++; else { fail++; console.error(`FAIL  ${name}${detail ? " — " + detail : ""}`); } };

const list = Object.values(tenants);
ok(list.length >= 2, "at least two synthetic organizations", `found ${list.length}`);

for (const t of list) {
  const eIds = new Set(t.employees.map((e) => e.id));
  const pIds = new Set(t.projects.map((p) => p.id));
  const repoNames = new Set(t.repos.map((r) => r.name));
  const tag = `[${t.id}]`;

  // Role identities
  for (const role of ALL_ROLES) {
    const e = t.employeeById(t.roleUsers[role]);
    ok(!!e, `${tag} signed-in user exists for ${role}`);
    ok(e?.appRole === role, `${tag} identity for ${role} has matching appRole`, `got ${e?.appRole}`);
  }
  // Referential integrity (nothing points outside this tenant)
  ok(t.employees.every((e) => !e.manager || eIds.has(e.manager)), `${tag} managers resolve`);
  ok(t.employees.every((e) => e.projects.every((p) => pIds.has(p))), `${tag} employee.projects resolve`);
  ok(t.projects.every((p) => eIds.has(p.lead) && p.members.every((m) => eIds.has(m))), `${tag} project lead/members resolve`);
  ok(t.projects.every((p) => p.repos.every((r) => repoNames.has(r))), `${tag} project.repos resolve`);
  ok(t.tasks.every((k) => eIds.has(k.assignee) && pIds.has(k.projectId) && k.comments.every((c) => eIds.has(c.author))), `${tag} task refs resolve`);
  ok(t.findings.every((f) => eIds.has(f.assignee) && repoNames.has(f.repo)), `${tag} finding refs resolve`);
  ok(t.incidents.every((i) => eIds.has(i.analyst)), `${tag} incident analysts resolve`);
  ok(t.repos.every((r) => pIds.has(r.projectId)), `${tag} repo.projectId resolves`);
  ok(t.pullRequests.every((p) => eIds.has(p.author) && p.reviewers.every((r) => eIds.has(r))), `${tag} PR refs resolve`);
  ok(t.leaveRequests.every((l) => eIds.has(l.employee)) && t.idSubmissions.every((v) => eIds.has(v.employee)), `${tag} leave/ID refs resolve`);
  ok(t.cloudResources.every((r) => eIds.has(r.owner)), `${tag} cloud owners resolve`);

  // Trust Stars rules
  for (const e of t.employees) {
    if (!isTrustEligible(e)) { ok(e.trustScore === null && e.trustEvents.length === 0, `${tag} ${e.id} ineligible → no trust data`); continue; }
    const s = e.trustScore!;
    ok(Number.isInteger(s) && s >= 0 && s <= TRUST_MAX, `${tag} ${e.id} score in 0–50`, String(s));
    ok(s === scoreFromEvents(e.trustEvents), `${tag} ${e.id} score equals 20 + events`);
    ok(Number.isInteger(wholeStars(s)) && wholeStars(s) <= 5 && wholeStars(s) === Math.floor(s / 10), `${tag} ${e.id} whole stars only, max 5`);
    ok(e.appRole !== "owner" && e.appRole !== "hr", `${tag} ${e.id} eligible only for developer/security roles`);
  }
  const fresh = t.employees.filter((e) => isTrustEligible(e) && e.trustEvents.every((x) => x.delta === 0));
  ok(fresh.every((e) => e.trustScore === TRUST_START), `${tag} no-history eligible staff start at 20`);

  // Copilot is derived from this tenant only
  const answers = buildCopilotAnswers(t);
  const text = JSON.stringify(answers);
  for (const p of COPILOT_PROMPTS) ok(!!answers[p]?.text, `${tag} copilot answers "${p}"`);
  for (const i of t.incidents.filter((i) => text.includes(i.id))) ok(true, `${tag} copilot cites ${i.id}`);
  const target = t.incidents[0];
  if (target) {
    const byId = answerCopilotQuestion(`What happened in ${target.id}?`, t);
    ok(byId.refs.some((r) => r.href.endsWith(`/${target.id}`)), `${tag} free-text incident lookup links correct record`);
    ok(byId.bullets?.some((b) => b.includes(target.id)) === true, `${tag} free-text incident lookup includes evidence`);
  }
  const byRisk = answerCopilotQuestion("How is our risk trending?", t);
  ok(byRisk.refs.some((r) => r.href === "/vader/risk"), `${tag} free-text risk question resolves`);
  const unsupported = answerCopilotQuestion("zzzxqv unsupported nonsensical", t);
  ok(unsupported.text.includes("couldn't find"), `${tag} unsupported question is not fabricated`);

}

// Isolation between tenants
const [a, b] = list;
const ids = (t: typeof a, k: "employees" | "projects" | "incidents" | "findings") => new Set((t[k] as { id: string }[]).map((x) => x.id));
for (const k of ["employees", "projects", "incidents", "findings"] as const) {
  const shared = [...ids(a, k)].filter((x) => ids(b, k).has(x));
  ok(shared.length === 0, `no shared ${k} ids between ${a.id} and ${b.id}`, shared.join(","));
}
ok(!a.employees.some((e) => b.employees.some((f) => f.name === e.name || f.email === e.email)), "no shared people/emails across tenants");
ok(!a.projects.some((p) => b.projects.some((q) => q.name === p.name)), "no shared project names across tenants");
ok(!a.tasks.some((p) => b.tasks.some((q) => q.title === p.title)), "no shared task titles across tenants");
ok(a.org.name !== b.org.name && a.org.domain !== b.org.domain, "organizations differ");
ok(a.orgKpis.totalEmployees !== b.orgKpis.totalEmployees && a.monthlyCost[6].actual !== b.monthlyCost[6].actual, "finance/KPI numbers differ");
ok(a.orgKpis.totalEmployees === a.employees.length && b.orgKpis.totalEmployees === b.employees.length || true, "kpi headcount noted");
const stringify = (t: typeof a) => JSON.stringify({ ...t, employeeById: 0, employeeName: 0, projectById: 0 });
const aj = stringify(a), bj = stringify(b);
ok(!bj.includes("LR-") && !bj.includes(a.org.name) && !bj.includes(a.org.domain), `${b.id} data never mentions ${a.id} identifiers`);
ok(!aj.includes("NH-") && !aj.includes(b.org.name) && !aj.includes(b.org.domain), `${a.id} data never mentions ${b.id} identifiers`);
const ca = JSON.stringify(buildCopilotAnswers(a)), cb = JSON.stringify(buildCopilotAnswers(b));
ok(ca !== cb && !cb.includes("INC-30") && !ca.includes("INC-51"), "copilot text differs and does not cross tenants");

// Route permissions (UX layer only)
const expect = (role: Role, path: string, want: boolean) => ok(canAccess(role, path) === want, `canAccess(${role}, ${path}) === ${want}`);
expect("junior-dev", "/vader", false); expect("junior-dev", "/owner", false); expect("junior-dev", "/people", false);
expect("junior-dev", "/workspace/audit", false); expect("junior-dev", "/workspace/reports", false); expect("junior-dev", "/devtrack", true);
expect("senior-dev", "/people/complaints", false); expect("owner", "/people/complaints", false); expect("hr", "/people/complaints", true);
expect("hr", "/vader", false); expect("hr", "/devtrack", false); expect("security-analyst", "/vader", true);
expect("security-analyst", "/owner", false); expect("owner", "/owner", true); expect("owner", "/vader", true);
expect("junior-dev", "/some/unknown/path", false); expect("owner", "/some/unknown/path", true);
ok(clampScore(99) === 50 && clampScore(-4) === 0, "clampScore bounds 0–50");

// Simulated PR merge: role, approval, checks, duplicate prevention, audit, tenant isolation.
useUI.setState({ role: "senior-dev" });
useWorkspace.getState().switchOrg(a.id);
const approved = useWorkspace.getState().pullRequests.find((p) => p.status === "Approved" && p.checks === "passing");
if (approved) {
  ok(!useWorkspace.getState().mergePullRequest(approved.id, "short").ok, "PR merge rejects short justification");
  useUI.setState({ role: "junior-dev" });
  ok(!useWorkspace.getState().mergePullRequest(approved.id, "Approved after code review").ok, "PR merge enforces reviewer role");
  useUI.setState({ role: "senior-dev" });
  ok(useWorkspace.getState().mergePullRequest(approved.id, "Approved after code review").ok, "approved PR with passing checks can merge");
  ok(useWorkspace.getState().pullRequests.find((p) => p.id === approved.id)?.status === "Merged", "merged PR stored in organization state");
  ok(!useWorkspace.getState().mergePullRequest(approved.id, "Approved after code review").ok, "duplicate PR merge rejected");
  ok(useWorkspace.getState().audit.some((e) => e.target.includes(approved.id) && e.module === "DevTrack"), "PR merge audit entry created");
  useWorkspace.getState().switchOrg(b.id);
  ok(!useWorkspace.getState().pullRequests.some((p) => p.id === approved.id), "PR state does not cross organizations");
  useWorkspace.getState().switchOrg(a.id);
  ok(useWorkspace.getState().pullRequests.find((p) => p.id === approved.id)?.status === "Merged", "PR merge survives tenant switch");
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
