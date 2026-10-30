/**
 * F2 People/HR verification (no browser): complaint privacy + workflow, promotion workflow, leave workflow,
 * tenant isolation of HR state. Exercises the real zustand store with the real permission rules.
 * Run: npm run verify:hr   (compiles with tsc to a temp dir, then runs with node; exit code 1 on failure)
 */
import { tenants } from "../lib/api/mock";
import { useWorkspace } from "../stores/workspace-store";
import { useUI } from "../stores/ui-store";
import { visibleComplaints, viewKind, visibleEvents } from "../lib/complaints";
import { validatePromotion, higherGrades, gradeOf, canDecide } from "../lib/promotions";
import { validateLeave, weekdaysBetween } from "../lib/leave";
import { canAccess } from "../lib/permissions";
import type { Role } from "../lib/types";

let pass = 0, fail = 0;
const ok = (c: boolean, n: string, d = "") => { if (c) pass++; else { fail++; console.error(`FAIL  ${n}${d ? " — " + d : ""}`); } };
const W = () => useWorkspace.getState();
const as = (org: string, role: Role) => { W().switchOrg(org); useUI.setState({ role }); };
const uid = (org: string, role: Role) => tenants[org].roleUsers[role];
const view = (org: string, role: Role) => visibleComplaints(W().complaints, { id: uid(org, role), role });
const today = new Date().toISOString().slice(0, 10);
const future = (days: number) => new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
const goodComplaint = { title: "Meeting room booking abuse", category: "Policy violation" as const, description: "A team keeps booking every meeting room for the whole day and never releases them, blocking others.", incidentDate: today, confidentiality: "Confidential" as const, anonymous: false };

for (const org of ["lumen", "northwind"]) {
  const d = tenants[org];
  const hrs = d.employees.filter((e) => e.appRole === "hr");
  // ── seed sanity + privacy
  as(org, "owner");
  ok(view(org, "owner").length === 0, `[${org}] Owner sees zero complaints`);
  ok(canAccess("owner", "/people/complaints") === false, `[${org}] Owner route blocked`);
  as(org, "senior-dev");
  ok(view(org, "senior-dev").length === 0, `[${org}] unrelated Senior Dev sees none`);
  ok(view(org, "security-analyst").length === 0, `[${org}] Security Analyst sees none`);
  const mine = view(org, "junior-dev");
  ok(mine.length >= 1 && mine.every((x) => x.c.submittedBy === uid(org, "junior-dev") && x.kind === "complainant"), `[${org}] junior sees only own complaints`);
  ok(mine.every((x) => visibleEvents(x.c, x.kind).every((e) => e.visibility === "complainant")), `[${org}] complainant never gets HR-only events`);
  // concerned person cannot see
  for (const c of d.complaints.filter((c) => c.concerning)) {
    const concerned = d.employeeById(c.concerning!)!;
    ok(viewKind(c, { id: concerned.id, role: concerned.appRole }) === "none", `[${org}] ${c.id}: person complained about has no access`);
  }
  // Restricted: only assignee sees contents, other HR redacted, involved HR none
  const restricted = d.complaints.filter((c) => c.confidentiality === "Restricted");
  ok(restricted.length >= 1, `[${org}] has a Restricted seed case`);
  for (const c of restricted) {
    const kinds = hrs.map((h) => viewKind(c, { id: h.id, role: "hr" }));
    ok(kinds.filter((k) => k === "reviewer").length === 1, `[${org}] ${c.id}: exactly one HR reviewer`, kinds.join());
    ok(kinds.includes("redacted") && kinds.includes("none"), `[${org}] ${c.id}: other HR redacted, concerned HR excluded`, kinds.join());
  }

  // ── complaint workflow
  as(org, "senior-dev");
  const bad = W().submitComplaint({ ...goodComplaint, title: "x", description: "short" });
  ok(!bad.ok, `[${org}] invalid complaint rejected`);
  ok(!W().submitComplaint({ ...goodComplaint, incidentDate: future(3) }).ok, `[${org}] future incident date rejected`);
  ok(!W().submitComplaint({ ...goodComplaint, confidentiality: "Restricted" }).ok, `[${org}] employees can't self-select Restricted`);
  ok(!W().submitComplaint({ ...goodComplaint, concerning: uid(org, "senior-dev") }).ok, `[${org}] can't file a complaint about yourself`);
  const before = W().complaints.length;
  const sub = W().submitComplaint(goodComplaint);
  ok(sub.ok && W().complaints.length === before + 1, `[${org}] valid complaint stored`);
  const id = sub.ok ? sub.id : "";
  ok(view(org, "senior-dev").some((x) => x.c.id === id && x.c.status === "Submitted"), `[${org}] submitter sees it in own history as Submitted`);
  as(org, "owner"); ok(!view(org, "owner").some((x) => x.c.id === id), `[${org}] Owner can't see new Confidential complaint`);
  ok(!W().setComplaintStatus(id, "Under review").ok, `[${org}] Owner can't change status`);
  as(org, "junior-dev"); ok(!W().setComplaintStatus(id, "Under review").ok && !view(org, "junior-dev").some((x) => x.c.id === id), `[${org}] unrelated employee blocked`);
  as(org, "senior-dev"); ok(!W().setComplaintStatus(id, "Under review").ok, `[${org}] submitter can't review own case`);
  const reviewer = hrs.find((h) => h.id !== uid(org, "senior-dev"))!;
  as(org, "hr");
  const hrId = uid(org, "hr");
  ok(view(org, "hr").some((x) => x.c.id === id && x.kind === "reviewer"), `[${org}] HR sees new case as reviewer`);
  ok(!W().setComplaintStatus(id, "Closed").ok, `[${org}] invalid transition Submitted→Closed rejected`);
  ok(!W().setComplaintStatus(id, "Resolved").ok, `[${org}] Resolved needs the resolve action`);
  ok(W().setComplaintStatus(id, "Under review", "Looking into it.").ok, `[${org}] Submitted→Under review`);
  ok(W().setComplaintStatus(id, "Investigating").ok, `[${org}] Under review→Investigating`);
  ok(!W().resolveComplaint(id, "Unsubstantiated", "too short").ok, `[${org}] resolution summary validated`);
  ok(W().addComplaintMessage(id, "Private reviewer note", true).ok && W().addComplaintMessage(id, "We are looking at this.").ok, `[${org}] HR can add internal note + message`);
  ok(W().resolveComplaint(id, "Resolved informally", "Agreed a booking limit with the team.").ok, `[${org}] resolve with outcome`);
  as(org, "senior-dev");
  const seen = view(org, "senior-dev").find((x) => x.c.id === id)!;
  ok(seen.c.status === "Resolved", `[${org}] submitter sees updated status Resolved`);
  const evs = visibleEvents(seen.c, seen.kind);
  ok(evs.some((e) => e.text.includes("We are looking")) && !evs.some((e) => e.text.includes("Private reviewer")), `[${org}] submitter sees messages but not internal notes`);
  ok(!W().withdrawComplaint(id).ok, `[${org}] can't withdraw a resolved case`);
  as(org, "hr");
  ok(W().setComplaintStatus(id, "Closed").ok && !W().setComplaintStatus(id, "Investigating").ok, `[${org}] Closed is terminal`);
  // withdraw by submitter
  as(org, "junior-dev");
  const s2 = W().submitComplaint({ ...goodComplaint, title: "Another valid complaint" });
  ok(s2.ok && W().withdrawComplaint(s2.ok ? s2.id : "").ok, `[${org}] submitter can withdraw open case`);
  // escalate: other HR loses content access
  as(org, "hr");
  const esc = W().submitComplaint({ ...goodComplaint, title: "HR-side complaint to escalate" }); // filed by HR → complainant tier only
  ok(esc.ok, `[${org}] HR can file own complaint`);
  const flip = view(org, "hr").find((x) => x.kind === "reviewer" && x.c.confidentiality !== "Restricted" && x.c.status !== "Closed" && x.c.status !== "Resolved" && x.c.status !== "Withdrawn");
  if (flip) { ok(W().escalateComplaint(flip.c.id).ok, `[${org}] escalate to Restricted`); }

  // ── promotions
  as(org, "junior-dev"); ok(!W().createPromotion({}).ok && !canAccess("junior-dev", "/people/promotions"), `[${org}] junior can't propose`);
  const ownerId = uid(org, "owner");
  as(org, "hr");
  const target = d.employees.find((e) => e.status === "Active" && e.appRole === "junior-dev" && !d.promotions.some((p) => p.employeeId === e.id))!;
  const grade = gradeOf(target);
  ok(higherGrades(grade).length > 0, `[${org}] grade ladder exists for ${grade}`);
  ok(!W().createPromotion({ employeeId: target.id, proposedRole: "Lead", proposedGrade: grade, effectiveDate: future(30), justification: "x".repeat(50) }).ok, `[${org}] same grade rejected`);
  ok(!W().createPromotion({ employeeId: target.id, proposedRole: "Lead", proposedGrade: higherGrades(grade)[0], effectiveDate: today.slice(0, 4) + "-01-01", justification: "x".repeat(50) }).ok, `[${org}] past effective date rejected`);
  ok(!W().createPromotion({ employeeId: target.id, proposedRole: "Lead", proposedGrade: higherGrades(grade)[0], effectiveDate: future(30), justification: "too short" }).ok, `[${org}] short justification rejected`);
  ok(!W().createPromotion({ employeeId: hrId, proposedRole: "Lead", proposedGrade: "E9", effectiveDate: future(30), justification: "x".repeat(50) }).ok, `[${org}] self-proposal rejected`);
  const pr = W().createPromotion({ employeeId: target.id, proposedRole: "Senior " + target.role, proposedGrade: higherGrades(grade)[0], effectiveDate: future(30), justification: "Consistently exceeded targets and mentors teammates across two projects." });
  ok(pr.ok, `[${org}] HR creates proposal`);
  const pid = pr.ok ? pr.id : "";
  ok(W().promotions[0].status === "Pending Owner approval", `[${org}] HR proposal waits for Owner`);
  ok(!W().createPromotion({ employeeId: target.id, proposedRole: "Lead", proposedGrade: higherGrades(grade)[0], effectiveDate: future(30), justification: "x".repeat(50) }).ok, `[${org}] duplicate open proposal rejected`);
  ok(!W().decidePromotion(pid, "Approved", "").ok, `[${org}] proposer (HR) can't approve own proposal`);
  as(org, "senior-dev"); ok(!W().decidePromotion(pid, "Approved", "").ok, `[${org}] dev can't decide`);
  as(org, "owner");
  ok(!W().decidePromotion(pid, "Rejected", "no").ok, `[${org}] rejection needs reason`);
  ok(W().decidePromotion(pid, "Approved", "Approved.").ok, `[${org}] Owner approves`);
  const done = W().promotions.find((p) => p.id === pid)!;
  ok(done.status === "Approved" && done.approvals.every((a) => a.state === "Approved"), `[${org}] status becomes Approved`);
  ok(!W().decidePromotion(pid, "Rejected", "Changed my mind later.").ok, `[${org}] decided proposal is final`);
  ok(d.employeeById(target.id)!.role === target.role && gradeOf(d.employeeById(target.id)!) === grade, `[${org}] approval doesn't alter employee record`);
  // owner-proposed → HR decides; reject path
  const t2 = d.employees.find((e) => e.status === "Active" && e.appRole === "senior-dev" && !W().promotions.some((p) => p.employeeId === e.id && p.status.startsWith("Pending")))!;
  const pr2 = W().createPromotion({ employeeId: t2.id, proposedRole: "Staff " + t2.role, proposedGrade: higherGrades(gradeOf(t2))[0], effectiveDate: future(60), justification: "Owns a critical service end to end and unblocked several teams this year." });
  ok(pr2.ok && W().promotions[0].status === "Pending HR review", `[${org}] Owner proposal waits for HR`);
  as(org, "hr");
  ok(W().decidePromotion(pr2.ok ? pr2.id : "", "Rejected", "Not enough evidence of staff-level scope yet.").ok && W().promotions[0].status === "Rejected", `[${org}] HR rejects → Rejected`);
  const seedPending = d.promotions.filter((p) => p.status.startsWith("Pending"));
  for (const p of seedPending) { const r: Role = p.status === "Pending HR review" ? "hr" : "owner"; ok(canDecide(p, r, uid(org, r)).ok || p.employeeId === uid(org, r), `[${org}] seed ${p.id} decidable by ${r}`); }

  // ── leave
  as(org, "junior-dev");
  const me = uid(org, "junior-dev");
  ok(!W().submitLeave({ type: "Annual leave", from: future(10), to: future(5), reason: "" }).ok, `[${org}] end before start rejected`);
  ok(!W().submitLeave({ type: "Annual leave", from: "2020-01-06", to: "2020-01-07", reason: "" }).ok, `[${org}] past start rejected`);
  ok(!W().submitLeave({ type: "Medical leave", from: future(10), to: future(11), reason: "" }).ok, `[${org}] medical note required`);
  const lv = W().submitLeave({ type: "Annual leave", from: future(40), to: future(44), reason: "Family trip" });
  ok(lv.ok, `[${org}] valid leave stored`);
  const lid = lv.ok ? lv.id : "";
  ok(!W().submitLeave({ type: "Casual leave", from: future(42), to: future(43), reason: "" }).ok, `[${org}] overlapping request rejected`);
  ok(W().leave.find((l) => l.id === lid)?.status === "Pending" && W().leave.find((l) => l.id === lid)?.employee === me, `[${org}] status tracked as Pending`);
  ok(!W().decideLeave(lid, "Approved").ok, `[${org}] requester can't approve own leave`);
  as(org, "senior-dev"); ok(!W().decideLeave(lid, "Approved").ok, `[${org}] developers can't review leave`);
  as(org, "hr");
  ok(!W().decideLeave(lid, "Rejected", "no").ok, `[${org}] decline needs reason`);
  ok(W().decideLeave(lid, "Approved").ok && W().leave.find((l) => l.id === lid)?.status === "Approved", `[${org}] HR approves`);
  ok(!W().decideLeave(lid, "Rejected", "Changed my mind").ok, `[${org}] decided leave is final`);
  as(org, "junior-dev");
  const lv2 = W().submitLeave({ type: "Casual leave", from: future(90), to: future(90), reason: "" });
  ok(lv2.ok && W().cancelLeave(lv2.ok ? lv2.id : "").ok, `[${org}] requester can cancel pending`);
}

// ── tenant isolation of HR state
as("lumen", "hr"); const lc = W().complaints.map((c) => c.id).join(); const lp = W().promotions.length;
as("northwind", "hr");
ok(W().complaints.every((c) => c.id.startsWith("NC-") || c.submittedBy.startsWith("NH-")), "northwind slice holds only northwind complaints");
ok(!W().complaints.some((c) => lc.includes(c.id) && c.id.startsWith("C-")), "no lumen complaint ids in northwind slice");
as("lumen", "hr");
ok(W().complaints.map((c) => c.id).join() === lc && W().promotions.length === lp, "switching back restores lumen HR state (no leakage from northwind actions)");

// ── pure helpers
ok(weekdaysBetween("2026-10-12", "2026-11-06") === 20, "weekdaysBetween matches seed (20)");
ok(higherGrades("N-S2").join() === "N-S3,N-S4,N-S5" && higherGrades("E7").length === 0 && higherGrades("Q1").length === 0, "grade ladders for E/N/N-S");
ok(Object.keys(validateLeave({}, { today, employeeId: "x", existing: [] })).length >= 3, "empty leave form yields field errors");
ok(Object.keys(validatePromotion({}, { proposerId: "x", existing: [], today })).length === 1, "promotion needs employee first");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
