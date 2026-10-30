"use client";
import * as React from "react";
import { BookOpen, Keyboard, MessageCircle, Search } from "lucide-react";
import { useTenant } from "@/stores/tenant-store";
import { useUI } from "@/stores/ui-store";
import { usePreferences, preferenceKey } from "@/stores/preferences-store";
import { Textarea } from "@/components/ui/input";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

const docs = [
  { t: "Getting started with MESH", c: "Basics", b: "Create your organization, verify your domain and invite HR. Each role sees the modules it needs." },
  { t: "How approvals work", c: "Owner", b: "Developers propose projects, senior developers endorse, and the owner approves with a note. Every decision is audited." },
  { t: "Understanding Trust Stars", c: "People", b: "A contextual signal built from reviewed events. It supports decisions and never judges trustworthiness on its own." },
  { t: "Authorizing repository scans", c: "DevTrack", b: "The demo checks a simulated authorization setting and displays seeded results. It does not clone repositories or run scanners." },
  { t: "Reading the risk score", c: "VADER", b: "Eight weighted components feed one score. Open the breakdown to see which signals contributed and why." },
  { t: "What is simulated in this prototype", c: "Basics", b: "Email codes, domain checks, OCR, scans, AI answers, payroll and access changes are simulated with mock data." },
];
const keys = [["Ctrl / Cmd + K", "Open the command palette"], ["Esc", "Close dialogs and drawers"], ["Enter", "Open the focused table row"], ["Tab", "Move between controls"]];

export default function HelpPage() {
  const org = useTenant((s) => s.orgId);
  const role = useUI((s) => s.role);
  const draft = usePreferences((s) => s.supportDrafts[preferenceKey(org, role)] ?? "");
  const saveDraft = usePreferences((s) => s.saveSupportDraft);
  const [q, setQ] = React.useState("");
  const list = docs.filter((d) => (d.t + d.b + d.c).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="space-y-6">
      <PageHeader title="Help and documentation" description="Guides, shortcuts and ways to reach us." />
      <div className="relative max-w-xl"><Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-ink-3" /><input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search documentation" placeholder="Search guides" className="h-12 w-full rounded-2xl border border-line-strong bg-white pl-11 pr-4 text-sm focus:border-violet focus:outline-none focus:ring-4 focus:ring-violet/15" /></div>
      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="grid gap-4 md:grid-cols-2">
          {list.length === 0 && <Card className="md:col-span-2"><EmptyState title="No guides found" description="Try different words." /></Card>}
          {list.map((d) => <Card key={d.t} hover><CardBody><div className="flex items-center gap-2 text-xs font-medium text-indigo"><BookOpen className="size-4" />{d.c}</div><h3 className="mt-2 font-display text-base font-semibold">{d.t}</h3><p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{d.b}</p></CardBody></Card>)}
        </div>
        <div className="space-y-4">
          <Card><CardHeader title="Keyboard shortcuts" icon={<Keyboard className="size-4 text-ink-3" />} /><CardBody><ul className="space-y-2.5 text-[13px]">{keys.map(([k, v]) => <li key={k} className="flex items-center justify-between gap-3"><span className="text-ink-2">{v}</span><kbd className="rounded-md border border-line bg-canvas px-2 py-0.5 text-xs">{k}</kbd></li>)}</ul></CardBody></Card>
          <Card><CardBody><MessageCircle className="size-6 text-indigo" /><h3 className="mt-3 font-display font-semibold">Talk to us</h3><p className="mt-1 text-[13px] text-ink-2">Questions about the prototype or feedback on the design?</p><form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); const message = String(new FormData(e.currentTarget).get("message") ?? "").trim(); if (message.length < 10) { toast.error("Describe the issue in at least 10 characters."); return; } saveDraft(org, role, message); toast.success("Support draft saved locally; no message sent"); }}><Textarea key={org + role} name="message" aria-label="Support message" defaultValue={draft} minLength={10} maxLength={5000} required /><Button type="submit" className="w-full" variant="soft">Save support draft</Button><p className="text-xs text-ink-3">Support delivery requires an integration. Copy this draft when contacting your administrator.</p></form></CardBody></Card>
        </div>
      </div>
    </div>
  );
}
