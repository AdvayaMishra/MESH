"use client";
import * as React from "react";
import { Info, ShieldQuestion } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { TrustStars } from "@/components/features/stat-pill";
import { useTrust } from "@/hooks/use-trust";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";
import { describeTrust, TRUST_MAX, TRUST_MAX_DELTA, TRUST_START } from "@/lib/trust";
import { fmtDate } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";
import type { Employee } from "@/lib/types";

export function TrustExplainer({ compact }: { compact?: boolean }) {
  return (
    <div className="flex gap-3 rounded-2xl border border-dashed border-violet/30 bg-tint-violet/60 p-3.5 text-[13px] text-ink-2">
      <ShieldQuestion className="mt-0.5 size-4 shrink-0 text-indigo" aria-hidden />
      <p>
        <span className="font-semibold text-ink">Trust Stars are decision support, not a verdict.</span>{" "}
        {compact
          ? `Scored 0–${TRUST_MAX} (one star per 10 points). Every change links to a visible event and a human reviewer.`
          : `Eligible developer and security roles start at ${TRUST_START} of ${TRUST_MAX} points (2 stars). Scores move only through reviewed events, by at most ${TRUST_MAX_DELTA} points at a time, and stay between 0 and ${TRUST_MAX}. Unusual-behavior signals never change a score on their own, and no score triggers an employment decision automatically.`}
      </p>
    </div>
  );
}

export function TrustSummary({ employee, size = 20 }: { employee: Employee; size?: number }) {
  const { eligible, score } = useTrust(employee);
  if (!eligible || score === null) {
    return <p className="rounded-xl border border-dashed border-line-strong p-4 text-sm text-ink-2">Trust Stars aren&apos;t used for this role. They apply to developer and security roles only.</p>;
  }
  return (
    <div className="space-y-2">
      <TrustStars score={score} size={size} />
      <p className="font-display text-2xl font-bold text-ink">
        {score} <span className="text-sm font-medium text-ink-3">/ {TRUST_MAX} points</span>
      </p>
      <Progress value={(score / TRUST_MAX) * 100} aria-label={describeTrust(score)} />
      <p className="text-xs text-ink-3">{describeTrust(score)}</p>
    </div>
  );
}

export function TrustHistory({ employee }: { employee: Employee }) {
  const { events, eligible } = useTrust(employee);
  if (!eligible) return null;
  return (
    <ol className="space-y-3 border-l border-line pl-4" aria-label="Trust event history">
      {events.map((e) => (
        <li key={e.id} className="relative">
          <span className="absolute -left-[21px] top-1 size-2.5 rounded-full bg-violet ring-4 ring-white" />
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={e.delta > 0 ? "mint" : e.delta < 0 ? "amber" : "neutral"}>{e.delta > 0 ? `+${e.delta} pts` : e.delta === 0 ? "No change" : `${e.delta} pts`}</Badge>
            <span className="text-[11px] text-ink-3">{fmtDate(e.date)} · {e.source}</span>
          </div>
          <p className="mt-1 text-[13px] text-ink">{e.reason}</p>
          <p className="mt-0.5 text-[11px] text-ink-3">{e.reviewedBy ? `Human review: ${e.reviewedBy}` : "System event"}</p>
        </li>
      ))}
    </ol>
  );
}

/** Lets HR / Owner record a reviewed event. Validated in the store; clearly simulated. */
export function RecordTrustEvent({ employee }: { employee: Employee }) {
  const role = useUI((s) => s.role);
  const { currentUser } = useDataset();
  const record = useWorkspace((s) => s.recordTrustEvent);
  const [delta, setDelta] = React.useState("1");
  const [reason, setReason] = React.useState("");
  const [source, setSource] = React.useState("People");
  const [error, setError] = React.useState<string | null>(null);
  const { eligible } = useTrust(employee);
  if (!eligible || (role !== "hr" && role !== "owner")) return null;
  const self = currentUser.id === employee.id;

  const submit = (ev: React.FormEvent) => {
    ev.preventDefault();
    const res = record(employee.id, Number(delta), reason, source);
    if (!res.ok) return setError(res.error);
    setError(null);
    setReason("");
    toast.success("Reviewed event recorded (simulated)", { description: `New score: ${res.score} / ${TRUST_MAX}. No employment decision was made.` });
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-3 rounded-2xl border border-line p-4" aria-label="Record a reviewed Trust event">
      <p className="flex items-center gap-1.5 text-sm font-semibold text-ink"><Info className="size-4" aria-hidden /> Record a reviewed event <Badge tone="amber">Simulated</Badge></p>
      {self && <p className="text-xs text-ink-2">You can&apos;t record events about yourself.</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Change (points)" htmlFor="tr-delta" hint={`Whole number, -${TRUST_MAX_DELTA} to +${TRUST_MAX_DELTA}`}>
          <Input id="tr-delta" type="number" min={-TRUST_MAX_DELTA} max={TRUST_MAX_DELTA} step={1} value={delta} onChange={(e) => setDelta(e.target.value)} disabled={self} />
        </Field>
        <Field label="Source" htmlFor="tr-source">
          <Select id="tr-source" value={source} onChange={(e) => setSource(e.target.value)} disabled={self}>
            {["People", "DevTrack", "Owner"].map((s) => <option key={s}>{s}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="What was reviewed?" htmlFor="tr-reason" error={error ?? undefined}>
        <Textarea id="tr-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Describe the reviewed event and evidence" disabled={self} aria-invalid={!!error} />
      </Field>
      <Button type="submit" size="sm" disabled={self}>Record event</Button>
    </form>
  );
}
