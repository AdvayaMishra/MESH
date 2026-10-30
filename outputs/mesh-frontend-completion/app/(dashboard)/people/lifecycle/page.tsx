"use client";
import * as React from "react";
import { ArrowRight, Check, Loader2, Minus, Plus, RotateCcw, ShieldAlert, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Avatar } from "@/components/ui/avatar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Stepper } from "@/components/features/auth/stepper";
import { useAdministration } from "@/stores/admin-store";
import { useTenant } from "@/stores/tenant-store";
import { useWorkspace } from "@/stores/workspace-store";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";

type Mode = "onboarding" | "offboarding";
interface Change { service: string; scope: string; kind: "add" | "remove"; current: boolean; approval: string; affects: string }

const plans: Record<Mode, Change[]> = {
  onboarding: [
    { service: "Google Workspace", scope: "Mailbox + Drive (member)", kind: "add", current: false, approval: "Auto", affects: "Email, calendar, shared drives" },
    { service: "Slack", scope: "#design, #general", kind: "add", current: false, approval: "Manager", affects: "Team channels" },
    { service: "MESH DevTrack", scope: "Junior developer role", kind: "add", current: false, approval: "Manager", affects: "Tasks, proposals" },
    { service: "GitHub", scope: "Read: {repo}", kind: "add", current: false, approval: "Senior developer", affects: "1 repository" },
  ],
  offboarding: [
    { service: "Google Workspace", scope: "Mailbox + Drive (member)", kind: "remove", current: true, approval: "HR + IT", affects: "Email forwarding for 30 days" },
    { service: "GitHub", scope: "Write: {repo}", kind: "remove", current: true, approval: "Senior developer", affects: "1 repository, {prs}" },
    { service: "AWS IAM", scope: "ReadOnly + ecs:Describe*", kind: "remove", current: true, approval: "Security analyst", affects: "Staging access, 2 saved queries" },
    { service: "MESH DevTrack", scope: "Senior developer role", kind: "remove", current: true, approval: "Owner", affects: "Reassign {task}" },
    { service: "Payroll", scope: "Final settlement", kind: "remove", current: true, approval: "HR + Finance", affects: "Final pay run" },
  ],
};

const stepNames = [{ label: "Select" }, { label: "Review" }, { label: "Simulate" }, { label: "Reversal" }];

function Workflow({ mode }: { mode: Mode }) {
  const { employees, repos, tasks: dsTasks, pullRequests, currentUser } = useDataset();
  const proposeLifecycle = useAdministration((s) => s.proposeLifecycle);
  const pool = employees.filter((e) => (mode === "onboarding" ? e.status === "Onboarding" : ["Offboarding", "Active"].includes(e.status) && e.appRole !== "owner"));
  const [empId, setEmpId] = React.useState(pool[0]?.id ?? "");
  const [step, setStep] = React.useState(0);
  const [run, setRun] = React.useState<number>(-1);
  const [reverted, setReverted] = React.useState(false);
  const log = useWorkspace((s) => s.log);
  const emp = employees.find((e) => e.id === empId);
  const empRepo = (emp && repos.find((r) => emp.projects.includes(r.projectId))?.name) ?? repos[0]?.name ?? "a repository";
  const empTask = (emp && dsTasks.find((t) => t.assignee === emp.id)?.key) ?? "open tasks";
  const nPrs = emp ? pullRequests.filter((p) => p.author === emp.id && p.status !== "Merged").length : 0;
  const changes = plans[mode].map((c) => ({ ...c, scope: c.scope.replace("{repo}", empRepo), affects: c.affects.replace("{repo}", empRepo).replace("{task}", empTask).replace("{prs}", `${nPrs} open pull request${nPrs === 1 ? "" : "s"}`) }));

  React.useEffect(() => {
    if (step !== 2) return;
    const t = setInterval(() => setRun((r) => (r >= changes.length ? r : r + 1)), 650);
    return () => clearInterval(t);
  }, [step, changes.length]);

  const finished = run >= changes.length;

  return (
    <div className="space-y-5">
      <Stepper steps={stepNames} current={step} />
      {step === 0 && (
        <Card><CardBody className="space-y-4">
          <label htmlFor={`emp-${mode}`} className="text-[13px] font-medium">{mode === "onboarding" ? "Who is joining?" : "Who is leaving?"}</label>
          <Select id={`emp-${mode}`} value={empId} onChange={(e) => setEmpId(e.target.value)}>
            {pool.map((e) => <option key={e.id} value={e.id}>{e.name} · {e.role}</option>)}
          </Select>
          {emp && <div className="flex items-center gap-3 rounded-2xl bg-canvas p-4"><Avatar name={emp.name} size={44} /><div><p className="font-medium">{emp.name}</p><p className="text-sm text-ink-2">{emp.role} · {emp.department} · {emp.id}</p></div></div>}
          <Button variant="gradient" onClick={() => setStep(1)} disabled={!emp}>Preview access changes <ArrowRight /></Button>
        </CardBody></Card>
      )}
      {step === 1 && (
        <Card>
          <CardHeader title="Proposed access changes" subtitle={`${emp?.name} · nothing changes until you simulate and approvers sign off`} action={<SimulatedTag />} />
          <CardBody className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <thead><tr className="text-xs text-ink-3"><th className="pb-2 font-medium">Service</th><th className="pb-2 font-medium">Current</th><th className="pb-2 font-medium">Proposed</th><th className="pb-2 font-medium">Affected</th><th className="pb-2 font-medium">Approval</th></tr></thead>
              <tbody className="divide-y divide-line">
                {changes.map((c) => (
                  <tr key={c.service + c.scope}>
                    <td className="py-3 font-medium">{c.service}</td>
                    <td className="py-3 text-ink-2">{c.current ? c.scope : <span className="text-ink-3">No access</span>}</td>
                    <td className="py-3"><span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", c.kind === "add" ? "bg-tint-mint text-[#008068]" : "bg-tint-coral text-[#c21d45]")}>{c.kind === "add" ? <Plus className="size-3" /> : <Minus className="size-3" />}{c.kind === "add" ? c.scope : `Remove ${c.scope}`}</span></td>
                    <td className="py-3 text-ink-2">{c.affects}</td>
                    <td className="py-3"><Badge tone={c.approval === "Auto" ? "neutral" : "amber"}>{c.approval}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-4 flex gap-2"><Button variant="secondary" onClick={() => setStep(0)}>Back</Button><Button variant="gradient" onClick={() => { setReverted(false); setRun(0); setStep(2); }}>Run simulation <ArrowRight /></Button></div>
          </CardBody>
        </Card>
      )}
      {step === 2 && (
        <Card>
          <CardHeader title="Simulated execution" subtitle="Showing what would happen. No external system is contacted." action={<SimulatedTag label="No real permissions changed" />} />
          <CardBody>
            <ul className="space-y-3" aria-live="polite">
              {changes.map((c, i) => (
                <li key={c.service + c.scope} className="flex items-center gap-3 rounded-xl border border-line px-4 py-3">
                  {run > i ? <span className="flex size-6 items-center justify-center rounded-full bg-tint-mint text-[#008068]"><Check className="size-3.5" /></span> : run === i ? <Loader2 className="size-5 animate-spin text-violet" /> : <span className="size-5 rounded-full border-2 border-line-strong" />}
                  <span className="flex-1 text-sm"><span className="font-medium">{c.service}</span> <span className="text-ink-2">· {c.kind === "add" ? "would grant" : "would revoke"} {c.scope}</span></span>
                  {run > i && <span className="text-xs text-ink-3">Simulated</span>}
                </li>
              ))}
            </ul>
            {finished && (
              <div className="mt-4 flex items-start gap-2.5 rounded-xl bg-tint-amber px-4 py-3 text-[13px] text-[#8a5200]"><ShieldAlert className="mt-0.5 size-4 shrink-0" /><span>Simulation complete. Real changes require each approver to confirm and an integration to confirm completion in the target system.</span></div>
            )}
            <div className="mt-4 flex gap-2"><Button variant="secondary" onClick={() => setStep(1)}>Back</Button><Button variant="gradient" disabled={!finished} onClick={() => { log({ actor: currentUser.name, action: `Simulated ${mode}`, target: `${emp?.id} ${emp?.name}`, module: "People", result: "Simulated" }); setStep(3); }}>See reversal plan <ArrowRight /></Button></div>
          </CardBody>
        </Card>
      )}
      {step === 3 && (
        <Card>
          <CardHeader title="Reversal preview" subtitle="Every change can be rolled back from this plan" action={reverted ? <Badge tone="mint" dot>Reverted (simulated)</Badge> : <SimulatedTag />} />
          <CardBody>
            <ol className="space-y-2.5">
              {[...changes].reverse().map((c, i) => (
                <li key={c.service + c.scope} className="flex items-center gap-3 rounded-xl bg-canvas px-4 py-3 text-sm"><Undo2 className="size-4 text-ink-3" /><span className="flex-1">{i + 1}. {c.kind === "add" ? "Revoke" : "Restore"} <span className="font-medium">{c.scope}</span> on {c.service}</span><Badge tone={reverted ? "mint" : "neutral"}>{reverted ? "Undone" : "Ready"}</Badge></li>
              ))}
            </ol>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" disabled={reverted} onClick={() => { setReverted(true); toast.success("Reversal simulated", { description: "Access returned to its previous state in the preview." }); }}><RotateCcw /> Simulate reversal</Button>
              <Button variant="gradient" onClick={() => { const result = proposeLifecycle(empId, mode); if (!result.ok) { toast.error(result.error); return; } toast.success("Plan saved to the demo approval queue; no email sent"); setStep(0); setRun(-1); }}>Save plan and request approvals</Button>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

export default function LifecyclePage() {
  const org = useTenant((s) => s.orgId);
  const plans = useAdministration((s) => s.organizations[org]?.plans);
  const transition = useAdministration((s) => s.transitionLifecycle);
  const { employeeName, currentUser } = useDataset();
  return (
    <div>
      <PageHeader title="Employee lifecycle" description="Guide people in and out with a preview of every access change and a way back." />
      <Tabs defaultValue="onboarding">
        <TabsList><TabsTrigger value="onboarding">Onboarding</TabsTrigger><TabsTrigger value="offboarding">Offboarding</TabsTrigger></TabsList>
        <TabsContent value="onboarding"><Workflow mode="onboarding" /></TabsContent>
        <TabsContent value="offboarding"><Workflow mode="offboarding" /></TabsContent>
      </Tabs>
      <Card className="mt-6"><CardHeader title="Lifecycle approval queue" subtitle="A different HR/owner reviewer approves. Execution changes demo employee status only; no external permissions change." /><CardBody className="space-y-3">
        {!plans?.length && <p className="text-sm text-ink-3">Save a plan from the workflow to begin review.</p>}
        {plans?.map((plan) => <div key={plan.id} className="rounded-xl border border-line p-4"><p className="font-semibold">{employeeName(plan.employeeId)} · {plan.mode}</p><p className="text-sm text-ink-3">{plan.status} · proposed by {employeeName(plan.proposedBy)}</p><div className="mt-3 flex gap-2">{(plan.status === "Pending" ? ["approve"] : plan.status === "Approved" ? ["execute"] : plan.status === "Executed" ? ["reverse"] : []).map((action) => <Button key={action} size="sm" variant="secondary" disabled={plan.employeeId === currentUser.id || (action === "approve" && plan.proposedBy === currentUser.id)} onClick={() => { const result = transition(plan.id, action as "approve" | "execute" | "reverse"); if (result.ok) toast.success(`Plan ${action} completed in the demo`); else toast.error(result.error); }}>{action === "approve" ? "Approve plan" : action === "execute" ? "Execute in demo" : "Reverse demo changes"}</Button>)}</div></div>)}
      </CardBody></Card>
    </div>
  );
}
