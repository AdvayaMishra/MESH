"use client";
import * as React from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CheckCircle2, FlaskConical, Play, RotateCcw, ShieldCheck } from "lucide-react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SeverityBadge, SimulatedTag } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { colors, type Severity } from "@/lib/design-tokens";
import { cn } from "@/lib/utils/cn";

interface Scenario { id: string; name: string; blurb: string; events: { t: string; text: string; sev: Severity }[]; detection: string; incident: string; risk: number[]; defenses: string[] }

const scenarios: Scenario[] = [
  { id: "login", name: "Suspicious login sequence", blurb: "Several failed logins followed by a success from a new country.",
    events: [{ t: "00:00", text: "6 failed logins for synthetic user sim-user-1", sev: "low" }, { t: "00:03", text: "Successful login from an unseen country", sev: "medium" }, { t: "00:04", text: "New device registered", sev: "medium" }, { t: "00:07", text: "Session reads 3 shared drives", sev: "high" }],
    detection: "Impossible-travel and credential-stuffing rules matched. Confidence 86%.", incident: "SIM-001 · Possible account takeover (medium)", risk: [30, 31, 36, 41, 47], defenses: ["Require MFA re-verification for the session", "Notify the account owner", "Add the source ASN to a watch list"] },
  { id: "api", name: "API traffic anomaly", blurb: "A key suddenly sends 10× its normal volume.",
    events: [{ t: "00:00", text: "Partner key sim-key-7 averages 120 req/min", sev: "info" }, { t: "00:02", text: "Rate climbs to 1,250 req/min", sev: "medium" }, { t: "00:03", text: "Sequential ID enumeration detected", sev: "high" }, { t: "00:05", text: "Rate limiter returns 429 for 41% of calls", sev: "medium" }], detection: "Volume and enumeration detectors fired together. Confidence 91%.", incident: "SIM-002 · API abuse (high)", risk: [30, 30, 34, 42, 44], defenses: ["Throttle the key to its baseline", "Contact the partner about a retry loop", "Enable response-size limits on the endpoint"] },
  { id: "priv", name: "Privilege change anomaly", blurb: "A role is granted admin rights outside the change window.",
    events: [{ t: "00:00", text: "Change window closed (no approved requests)", sev: "info" }, { t: "00:02", text: "Role sim-role-deploy gains AdministratorAccess", sev: "high" }, { t: "00:03", text: "First use of the new permissions", sev: "high" }], detection: "Out-of-window IAM change with no linked ticket. Confidence 94%.", incident: "SIM-003 · Unapproved privilege change (high)", risk: [30, 31, 45, 50], defenses: ["Revert the policy attachment", "Require a ticket reference for admin grants", "Review actions taken with the role"] },
  { id: "data", name: "Abnormal data access", blurb: "A service reads far more rows than usual, then exports them.",
    events: [{ t: "00:00", text: "sim-svc reads about 2k rows per hour", sev: "info" }, { t: "00:04", text: "Full-table read of a customers table (1.2M rows)", sev: "high" }, { t: "00:06", text: "600 MB export to an unapproved endpoint", sev: "critical" }], detection: "Row-count and egress detectors correlated into one chain. Confidence 89%.", incident: "SIM-004 · Possible data exfiltration (critical)", risk: [30, 32, 52, 64], defenses: ["Block the destination", "Revoke the service credential", "Snapshot access logs for review"] },
  { id: "cloud", name: "Cloud misconfiguration", blurb: "A storage bucket is made public by a template update.",
    events: [{ t: "00:00", text: "Infrastructure template v42 applied", sev: "info" }, { t: "00:01", text: "Bucket sim-bucket policy allows public read", sev: "high" }, { t: "00:03", text: "Posture scan flags public exposure", sev: "high" }], detection: "Configuration drift rule matched. Confidence 97%.", incident: "SIM-005 · Public storage exposure (high)", risk: [30, 30, 40, 43], defenses: ["Block public access at the account level", "Fix the template and redeploy", "Check access logs for outside reads"] },
];

export default function SimulationPage() {
  const [id, setId] = React.useState(scenarios[0].id);
  const [step, setStep] = React.useState(-1);
  const s = scenarios.find((x) => x.id === id)!;
  const running = step >= 0 && step < s.events.length + 2;
  const finished = step >= s.events.length + 1;

  React.useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => setStep((x) => x + 1), 900);
    return () => clearTimeout(t);
  }, [step, running]);

  const shown = Math.min(Math.max(step, 0), s.events.length);
  const riskData = s.risk.map((v, i) => ({ t: i === 0 ? "Start" : `T+${i}`, risk: v })).slice(0, Math.max(1, Math.min(s.risk.length, shown + 1)));

  return (
    <div className="space-y-6">
      <PageHeader title="Attack simulation lab" description="Replay safe, synthetic scenarios to see how VADER detects, correlates and recommends a response." badge={<SimulatedTag label="Synthetic events only" />} />
      <div className="flex items-start gap-3 rounded-2xl border border-mint/40 bg-tint-mint p-4 text-[13.5px] text-[#065f4d]"><ShieldCheck className="mt-0.5 size-4 shrink-0" /><p><strong>No real activity is generated.</strong> These scenarios run entirely in your browser using made-up identities and resources. Nothing is sent to any network, system or person.</p></div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {scenarios.map((x) => (
          <button key={x.id} onClick={() => { setId(x.id); setStep(-1); }} aria-pressed={id === x.id} className={cn("card card-hover p-4 text-left", id === x.id && "!border-violet ring-4 ring-violet/10")}>
            <FlaskConical className={cn("size-5", id === x.id ? "text-violet" : "text-ink-3")} />
            <p className="mt-2.5 text-[13.5px] font-semibold leading-snug">{x.name}</p><p className="mt-1 text-xs text-ink-2">{x.blurb}</p>
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Button variant="gradient" onClick={() => setStep(0)} disabled={running}><Play /> {finished ? "Run again" : "Run simulation"}</Button>
        {step >= 0 && <Button variant="secondary" onClick={() => setStep(-1)}><RotateCcw /> Reset</Button>}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Simulated events" subtitle={step < 0 ? "Press Run to start" : `${shown} of ${s.events.length} events`} action={<SimulatedTag />} />
          <CardBody>
            {step < 0 ? <p className="py-10 text-center text-sm text-ink-2">Events will stream in here as the scenario plays.</p> : (
              <ol className="space-y-3 border-l border-line pl-5" aria-live="polite">
                {s.events.slice(0, shown).map((e, i) => (
                  <motion.li key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="relative"><span className="absolute -left-[26px] top-1 size-3 rounded-full ring-4 ring-white" style={{ background: e.sev === "critical" ? colors.coral : e.sev === "high" ? "#FF8A3D" : e.sev === "medium" ? colors.amber : colors.sky }} />
                    <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-[11px] text-ink-3">{e.t}</span><SeverityBadge severity={e.sev} /></div><p className="mt-0.5 text-[13.5px]">{e.text}</p></motion.li>
                ))}
              </ol>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Risk change" subtitle="Overall risk as events are detected" />
          <CardBody><div className="h-56" role="img" aria-label="Area chart of simulated risk change"><ResponsiveContainer width="100%" height="100%"><AreaChart data={riskData} margin={{ left: -22, right: 8, top: 8 }}>
            <defs><linearGradient id="simR" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors.coral} stopOpacity={0.35} /><stop offset="100%" stopColor={colors.coral} stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid vertical={false} stroke="#EEF1FA" /><XAxis dataKey="t" {...axisProps} /><YAxis {...axisProps} domain={[20, 80]} /><Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="risk" name="Risk" stroke={colors.coral} strokeWidth={3} fill="url(#simR)" /></AreaChart></ResponsiveContainer></div></CardBody>
        </Card>
      </div>

      {step >= s.events.length && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4 lg:grid-cols-3">
          <Card><CardHeader title="Detection result" /><CardBody><p className="flex items-start gap-2 text-[14px]"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />{s.detection}</p></CardBody></Card>
          <Card><CardHeader title="Correlated incident" /><CardBody><p className="text-[14px] font-medium">{s.incident}</p><Badge tone="amber" dot className="mt-2">Simulated, not saved</Badge></CardBody></Card>
          <Card><CardHeader title="Suggested defensive response" /><CardBody><ul className="space-y-2 text-[13.5px]">{s.defenses.map((d) => <li key={d} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-violet" />{d}</li>)}</ul></CardBody></Card>
        </motion.div>
      )}
    </div>
  );
}
