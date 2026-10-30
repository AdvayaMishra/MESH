"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Building2, CalendarDays, Mail, MapPin, ShieldCheck } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge, VerificationBadge } from "@/components/features/people/shared";
import { RecordTrustEvent, TrustExplainer, TrustHistory, TrustSummary } from "@/components/features/trust-panel";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtDate } from "@/lib/utils/format";
import { PriorityBadge } from "@/components/features/owner/approvals";
import { useDataset } from "@/lib/api";

const perms: Record<string, string[]> = {
  owner: ["Billing and spend", "Project approvals", "All modules", "Audit log"],
  hr: ["People directory", "Payroll and leave", "ID verification", "Audit log (people)"],
  "senior-dev": ["DevTrack projects", "Review proposals", "Repository scans", "Security findings"],
  "junior-dev": ["DevTrack tasks", "Submit proposals", "Own findings"],
  "security-analyst": ["VADER incidents", "Cloud inventory", "Response actions (approval required)", "DevTrack findings"],
};

export default function EmployeeProfilePage() {
  const { employeeById, employeeName } = useDataset();
  const { id } = useParams<{ id: string }>();
  const e = employeeById(id);
  const projects = useWorkspace((s) => s.projects);
  const audit = useWorkspace((s) => s.audit);
  const allLeave = useWorkspace((s) => s.leave);
  const promotions = useWorkspace((s) => s.promotions);
  if (!e) return <EmptyState title="Employee not found" description={`No employee has the ID ${id}.`} action={<Button asChild variant="secondary"><Link href="/people/directory">Back to directory</Link></Button>} />;

  const myProjects = projects.filter((p) => e.projects.includes(p.id));
  const leave = allLeave.filter((l) => l.employee === e.id);
  const timeline = [
    { d: e.joinDate, t: `Joined as ${e.role}`, s: "People" },
    ...(e.status === "Probation" ? [{ d: "2026-11-19", t: "Probation review due", s: "People" }] : []),
    ...(e.verification === "Verified" ? [{ d: e.joinDate, t: "Identity verified by a reviewer", s: "People" }] : []),
    ...(e.department !== "Sales" && e.appRole === "senior-dev" ? [{ d: "2024-04-01", t: "Promoted to senior engineer", s: "People" }] : []),
  ...promotions.filter((p) => p.employeeId === e.id && p.status !== "Withdrawn").map((p) => ({ d: p.createdAt.slice(0, 10), t: `Promotion to ${p.proposedRole} (${p.proposedGrade}): ${p.status}`, s: "People" })),
  ].sort((a, b) => b.d.localeCompare(a.d));
  const events = audit.filter((a) => a.target.includes(e.id) || a.actor === e.name).slice(0, 5);

  return (
    <div className="space-y-6">
      <Link href="/people/directory" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 hover:text-ink"><ArrowLeft className="size-4" /> Directory</Link>
      <Card className="overflow-hidden">
        <div className="h-24 gradient-mint opacity-90" />
        <div className="-mt-10 flex flex-col gap-4 px-6 pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-end gap-4">
            <Avatar name={e.name} size={84} className="!ring-4" />
            <div className="pb-1">
              <h1 className="font-display text-2xl font-bold">{e.name}</h1>
              <p className="text-sm text-ink-2">{e.role} · {e.department}</p>
              <div className="mt-2 flex flex-wrap gap-2"><StatusBadge status={e.status} /><VerificationBadge status={e.verification} /><Badge tone="neutral">{e.id}</Badge></div>
            </div>
          </div>
          <div className="flex gap-2"><Button variant="secondary" asChild><a href={`mailto:${e.email}`}><Mail /> Email</a></Button><Button variant="soft" asChild><Link href="/people/lifecycle">Change access</Link></Button></div>
        </div>
      </Card>

      <Tabs defaultValue="overview">
        <TabsList>
          {["overview", "projects", "leave", "access", "trust", "audit"].map((t) => <TabsTrigger key={t} value={t} className="capitalize">{t === "trust" ? "Trust Stars" : t === "audit" ? "Audit history" : t}</TabsTrigger>)}
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader title="Personal and organizational" /><CardBody>
              <dl className="grid gap-4 sm:grid-cols-2 text-sm">
                {[[Mail, "Work email", e.email], [Building2, "Department", e.department], [MapPin, "Location", e.location], [CalendarDays, "Join date", fmtDate(e.joinDate)], [ShieldCheck, "Manager", e.manager ? employeeName(e.manager) : "—"], [Building2, "Pay band", e.salaryBand]].map(([Icon, k, v]) => {
                  const I = Icon as typeof Mail;
                  return <div key={String(k)} className="flex gap-3"><I className="mt-0.5 size-4 text-ink-3" /><div><dt className="text-xs text-ink-3">{String(k)}</dt><dd className="font-medium text-ink break-all">{String(v)}</dd></div></div>;
                })}
              </dl></CardBody></Card>
            <Card><CardHeader title="Employment timeline" /><CardBody>
              <ol className="space-y-4 border-l border-line pl-5">
                {timeline.map((t, i) => <li key={i} className="relative"><span className="absolute -left-[26px] top-1 size-3 rounded-full bg-mint ring-4 ring-white" /><p className="text-sm font-medium text-ink">{t.t}</p><p className="text-xs text-ink-3">{fmtDate(t.d)} · {t.s}</p></li>)}
              </ol></CardBody></Card>
          </div>
        </TabsContent>

        <TabsContent value="projects">
          <Card><CardBody>
            {myProjects.length === 0 ? <EmptyState title="No assigned projects" description="Projects this person works on appear here." /> : (
              <ul className="divide-y divide-line">{myProjects.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 py-3"><div><Link href={`/devtrack/projects/${p.id}`} className="font-medium hover:text-indigo">{p.name}</Link><p className="text-xs text-ink-3">{p.key} · {p.progress}% complete</p></div><PriorityBadge priority={p.priority} /></li>
              ))}</ul>
            )}
          </CardBody></Card>
        </TabsContent>

        <TabsContent value="leave">
          <Card><CardBody>
            {leave.length === 0 ? <EmptyState title="No leave on record" description="Requests and approved leave show up here." /> : (
              <ul className="divide-y divide-line">{leave.map((l) => <li key={l.id} className="flex items-center justify-between py-3 text-sm"><div><p className="font-medium">{l.type}</p><p className="text-xs text-ink-3">{fmtDate(l.from)} – {fmtDate(l.to)} · {l.days} days</p></div><Badge tone={l.status === "Approved" ? "mint" : l.status === "Pending" ? "amber" : l.status === "Rejected" ? "coral" : "neutral"} dot>{l.status}</Badge></li>)}</ul>
            )}
          </CardBody></Card>
        </TabsContent>

        <TabsContent value="access">
          <Card><CardHeader title="Access permissions" subtitle="Derived from the assigned role" /><CardBody>
            <div className="flex flex-wrap gap-2">{(perms[e.appRole] ?? []).map((p) => <Badge key={p} tone="violet">{p}</Badge>)}</div>
          </CardBody></Card>
        </TabsContent>

        <TabsContent value="trust">
          <Card><CardHeader title="Trust Stars" subtitle="Contextual decision-support, reviewed by people" /><CardBody className="space-y-4">
            <TrustSummary employee={e} size={18} />
            <TrustExplainer />
            <TrustHistory employee={e} />
            <RecordTrustEvent employee={e} />
          </CardBody></Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card><CardBody>
            {events.length === 0 ? <EmptyState title="No recent audit events" /> : (
              <ul className="divide-y divide-line">{events.map((a) => <li key={a.id} className="flex items-center justify-between py-3 text-sm"><div><p className="font-medium">{a.action}</p><p className="text-xs text-ink-3">{a.actor} · {a.target} · {fmtDate(a.at)}</p></div><Badge tone={a.result === "Success" ? "mint" : a.result === "Denied" ? "coral" : "amber"}>{a.result}</Badge></li>)}</ul>
            )}
          </CardBody></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
