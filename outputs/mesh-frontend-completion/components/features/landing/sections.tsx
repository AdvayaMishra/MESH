"use client";
import * as React from "react";
import Link from "next/link";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import {
  ArrowRight, Bot, BriefcaseBusiness, Check, Code2, Fingerprint, Gauge, KeyRound, Lock, Network, Plus, Radar, ScanSearch,
  ShieldCheck, Sparkles, Users, Wallet, Eye, FileCheck2, Workflow, Bell,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ChartTooltip, axisProps } from "@/components/charts/chart-kit";
import { cn } from "@/lib/utils/cn";
import { colors } from "@/lib/design-tokens";

function SectionHead({ title, body, align = "center" }: { title: string; body: string; align?: "center" | "left" }) {
  return (
    <div className={cn("max-w-2xl", align === "center" && "mx-auto text-center")}>
      <h2 className="font-display text-3xl font-extrabold text-ink sm:text-[40px] sm:leading-[1.1]">{title}</h2>
      <p className="mt-4 text-[17px] leading-relaxed text-ink-2">{body}</p>
    </div>
  );
}

/* ------------------------------- Modules ------------------------------- */
const modules = [
  { name: "MESH Owner", tag: "Run the organization", icon: BriefcaseBusiness, href: "/owner", grad: "gradient-violet", tint: "bg-tint-violet", text: "text-indigo",
    points: ["Cloud spend and budget forecasting", "Project approvals with audit notes", "AI What-If Studio"] },
  { name: "MESH People", tag: "Look after your people", icon: Users, href: "/people", grad: "gradient-mint", tint: "bg-tint-mint", text: "text-[#008068]",
    points: ["Verified onboarding and ID review", "Payroll and leave with discrepancy checks", "Reversible offboarding previews"] },
  { name: "DevTrack", tag: "Ship with confidence", icon: Code2, href: "/devtrack", grad: "gradient-cyan", tint: "bg-tint-sky", text: "text-[#0b78b0]",
    points: ["Kanban, sprints and proposals", "Semgrep, Bandit, Gitleaks and OSV findings", "Consent-based repository scanning"] },
  { name: "VADER", tag: "See threats as one story", icon: Radar, href: "/vader", grad: "gradient-coral", tint: "bg-tint-coral", text: "text-[#c21d45]",
    points: ["Attack-chain correlation", "Explainable risk scoring", "AI Copilot and safe simulation lab"] },
];

export function Modules() {
  return (
    <section id="modules" className="mx-auto max-w-7xl scroll-mt-20 px-5 py-24 sm:px-8">
      <SectionHead title="Four modules. One shared source of truth." body="Each team gets a workspace shaped around its job. Everything shares the same people, projects and context, so nothing is retyped or out of date." />
      <div className="mt-14 grid gap-5 md:grid-cols-2">
        {modules.map((m) => (
          <Link key={m.name} href={m.href} className="group card card-hover relative overflow-hidden p-7">
            <div className={cn("absolute -right-12 -top-12 size-44 rounded-full opacity-20 blur-2xl transition-opacity group-hover:opacity-40", m.grad)} />
            <div className="relative">
              <span className={cn("flex size-12 items-center justify-center rounded-2xl text-white shadow-lg", m.grad)}><m.icon className="size-6" /></span>
              <h3 className="mt-5 font-display text-2xl font-bold">{m.name}</h3>
              <p className={cn("mt-1 text-sm font-medium", m.text)}>{m.tag}</p>
              <ul className="mt-5 space-y-2.5">
                {m.points.map((p) => (
                  <li key={p} className="flex items-start gap-2.5 text-[15px] text-ink-2"><Check className={cn("mt-0.5 size-4 shrink-0", m.text)} />{p}</li>
                ))}
              </ul>
              <span className={cn("mt-6 inline-flex items-center gap-1.5 text-sm font-semibold", m.text)}>Open {m.name} <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" /></span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

/* --------------------------- Product showcase --------------------------- */
function Frame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-[22px] border border-line bg-white shadow-pop">
      <div className="flex items-center gap-2 border-b border-line bg-canvas px-4 py-3">
        <span className="size-2.5 rounded-full bg-coral/70" /><span className="size-2.5 rounded-full bg-amber/80" /><span className="size-2.5 rounded-full bg-mint/80" />
        <span className="mx-auto rounded-md bg-white px-12 py-1 text-xs text-ink-3">{title}</span>
      </div>
      <div className="p-5 sm:p-6">{children}</div>
    </div>
  );
}

const mini = (label: string, value: string, tone: string) => (
  <div key={label} className={cn("rounded-xl p-3.5", tone)}>
    <p className="text-[11px] opacity-75">{label}</p>
    <p className="font-display text-xl font-bold">{value}</p>
  </div>
);

function OwnerPreview() {
  const bars = [38, 52, 46, 64, 58, 76, 70, 88];
  return (
    <Frame title="mesh.app/owner">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {mini("Employees", "24", "bg-tint-violet text-indigo")}
        {mini("Cloud spend", "$123.7k", "bg-tint-amber text-[#a86500]")}
        {mini("Approvals", "3", "bg-tint-sky text-[#0b78b0]")}
        {mini("Posture", "82", "bg-tint-mint text-[#008068]")}
      </div>
      <div className="mt-4 flex h-40 items-end gap-2 rounded-2xl bg-canvas p-4">
        {bars.map((h, i) => (
          <div key={i} className="flex-1 rounded-t-lg gradient-violet transition-all" style={{ height: `${h}%`, opacity: 0.45 + i * 0.07 }} />
        ))}
      </div>
    </Frame>
  );
}
function PeoplePreview() {
  const rows = [["Priya Raghunathan", "Head of People", "Verified", "mint"], ["Yuki Tanaka", "UX Researcher", "Pending review", "amber"], ["Grace Liu", "Data Engineer", "Pending review", "amber"], ["Samuel Osei", "Software Engineer I", "Needs resubmission", "coral"]];
  const tone: Record<string, string> = { mint: "bg-tint-mint text-[#008068]", amber: "bg-tint-amber text-[#a86500]", coral: "bg-tint-coral text-[#c21d45]" };
  return (
    <Frame title="mesh.app/people/verification">
      <ul className="divide-y divide-line">
        {rows.map(([n, r, s, t]) => (
          <li key={n} className="flex items-center justify-between gap-3 py-3">
            <div><p className="text-sm font-semibold">{n}</p><p className="text-xs text-ink-3">{r}</p></div>
            <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", tone[t])}>{s}</span>
          </li>
        ))}
      </ul>
    </Frame>
  );
}
function DevPreview() {
  const cols = [["To do", ["Rate limit search API", "Map clustering"], "bg-[#eef1fa]"], ["In progress", ["WebSocket backoff", "Signed artifacts"], "bg-tint-amber"], ["Done", ["Backfill thresholds"], "bg-tint-mint"]] as const;
  return (
    <Frame title="mesh.app/devtrack/board">
      <div className="grid grid-cols-3 gap-3">
        {cols.map(([t, items, bg]) => (
          <div key={t} className={cn("rounded-2xl p-2.5", bg)}>
            <p className="px-1.5 pb-2 text-xs font-semibold text-ink-2">{t}</p>
            <div className="space-y-2">{items.map((i) => <div key={i} className="rounded-xl bg-white p-2.5 text-xs font-medium shadow-sm">{i}</div>)}</div>
          </div>
        ))}
      </div>
    </Frame>
  );
}
function VaderPreview() {
  const steps = [["Unusual login", "#FFB547"], ["New device", "#FFB547"], ["API abuse", "#FF8A3D"], ["Privilege escalation", "#FF8A3D"], ["Database access", "#FF8A3D"], ["Large download", "#FF6B8A"]];
  return (
    <Frame title="mesh.app/vader/attack-chain">
      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-[560px] items-start">
          {steps.map(([l, c], i) => (
            <div key={l} className="flex flex-1 flex-col items-center text-center">
              <div className="flex w-full items-center">
                <span className={cn("h-0.5 flex-1", i === 0 && "opacity-0")} style={{ background: c }} />
                <span className="size-5 rounded-full ring-4 ring-white" style={{ background: c, boxShadow: `0 0 0 6px ${c}2e` }} />
                <span className={cn("h-0.5 flex-1", i === steps.length - 1 && "opacity-0")} style={{ background: c }} />
              </div>
              <p className="mt-3 px-1 text-[11px] font-medium leading-tight text-ink">{l}</p>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-5 rounded-xl bg-tint-coral px-3.5 py-2.5 text-[13px] text-[#9d1a3c]">Six correlated signals, one incident. Risk score moved from 34 to 71.</p>
    </Frame>
  );
}

export function ProductShowcase() {
  return (
    <section id="product" className="scroll-mt-20 bg-white py-24">
      <div className="mx-auto max-w-5xl px-5 sm:px-8">
        <SectionHead title="See each workspace at work" body="Switch between modules to see what each team opens first thing in the morning." />
        <Tabs defaultValue="owner" className="mt-12">
          <div className="flex justify-center">
            <TabsList className="!rounded-2xl">
              {[["owner", "Owner"], ["people", "People"], ["dev", "DevTrack"], ["vader", "VADER"]].map(([v, l]) => (
                <TabsTrigger key={v} value={v} className="px-4 py-2 text-sm">{l}</TabsTrigger>
              ))}
            </TabsList>
          </div>
          <TabsContent value="owner" className="mt-8"><OwnerPreview /></TabsContent>
          <TabsContent value="people" className="mt-8"><PeoplePreview /></TabsContent>
          <TabsContent value="dev" className="mt-8"><DevPreview /></TabsContent>
          <TabsContent value="vader" className="mt-8"><VaderPreview /></TabsContent>
        </Tabs>
      </div>
    </section>
  );
}

/* ------------------------------ Intelligence ------------------------------ */
export function Intelligence() {
  const items = [
    { icon: Sparkles, title: "What-If Studio", body: "Ask how a cloud change affects spend and capacity. Every answer lists its assumptions." },
    { icon: Bot, title: "VADER Copilot", body: "Summaries of incidents with evidence links, so you can verify each claim in one click." },
    { icon: Gauge, title: "Explainable scores", body: "Risk and Trust Stars show their inputs and history. Nothing is a black box." },
  ];
  return (
    <section id="intelligence" className="scroll-mt-20 overflow-hidden py-24">
      <div className="mx-auto grid max-w-7xl items-center gap-12 px-5 sm:px-8 lg:grid-cols-[1fr_1.1fr]">
        <div>
          <SectionHead align="left" title="Intelligence that shows its work" body="MESH suggests, summarises and simulates. People decide. Every recommendation comes with the evidence and assumptions behind it." />
          <ul className="mt-8 space-y-5">
            {items.map((i) => (
              <li key={i.title} className="flex gap-4">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-tint-violet text-indigo"><i.icon className="size-5" /></span>
                <div><p className="font-display font-semibold">{i.title}</p><p className="mt-1 text-[15px] text-ink-2">{i.body}</p></div>
              </li>
            ))}
          </ul>
        </div>
        <div className="relative">
          <div className="absolute -inset-6 rounded-[40px] bg-gradient-to-br from-lavender/30 via-transparent to-cyan/30 blur-2xl" />
          <div className="relative rounded-[24px] border border-violet/20 bg-white p-5 shadow-pop sm:p-6">
            <div className="flex items-center gap-2 text-xs font-semibold text-indigo"><Sparkles className="size-4" /> VADER Copilot <span className="ml-auto rounded-full border border-dashed border-amber/60 bg-tint-amber px-2 py-0.5 text-[10px] font-medium text-[#a86500]">Simulated</span></div>
            <div className="mt-4 ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-violet px-4 py-2.5 text-sm text-white">Why did our risk score increase?</div>
            <div className="mt-3 max-w-[92%] rounded-2xl rounded-bl-md border border-line bg-canvas p-4 text-sm leading-relaxed text-ink">
              Risk rose from 34 to 55 in three days, driven by three signals:
              <ul className="mt-2 space-y-1.5 text-[13px] text-ink-2">
                <li>• Identity and API anomalies on one service account <span className="rounded bg-tint-violet px-1.5 py-0.5 text-[11px] font-medium text-indigo">INC-3021</span></li>
                <li>• A public storage bucket <span className="rounded bg-tint-violet px-1.5 py-0.5 text-[11px] font-medium text-indigo">INC-3022</span></li>
                <li>• An out-of-window admin role change <span className="rounded bg-tint-violet px-1.5 py-0.5 text-[11px] font-medium text-indigo">INC-3024</span></li>
              </ul>
              <p className="mt-3 text-xs text-ink-3">These are signals for investigation, not proof of intent.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------ Security-first ------------------------------ */
export function SecurityFirst() {
  const items = [
    { icon: Fingerprint, title: "Verified identities", body: "Owners prove domain control and employees pass human-reviewed ID checks before they get access." },
    { icon: KeyRound, title: "Least privilege", body: "Five roles, each with its own navigation and permissions. Access changes are previewed and reversible." },
    { icon: ScanSearch, title: "Consent-based scanning", body: "Repositories are scanned only with explicit authorization, cloned temporarily and cleaned up after." },
    { icon: Lock, title: "Secrets never shown", body: "Detected credentials are redacted. MESH shows where they are, never what they are." },
    { icon: FileCheck2, title: "Audit everything", body: "Approvals, access changes and exports are written to a searchable audit log." },
    { icon: Eye, title: "Honest simulations", body: "Anything simulated is labeled as such, so a mock result is never mistaken for a real one." },
  ];
  return (
    <section id="security" className="scroll-mt-20 bg-[#172033] py-24 text-white">
      <div className="mx-auto max-w-7xl px-5 sm:px-8">
        <div className="max-w-2xl">
          <h2 className="font-display text-3xl font-extrabold sm:text-[40px] sm:leading-[1.1]">Security-first architecture</h2>
          <p className="mt-4 text-[17px] leading-relaxed text-white/70">Built around the idea that a platform holding your people and your code has to earn trust at every step.</p>
        </div>
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((i) => (
            <div key={i.title} className="rounded-3xl border border-white/10 bg-white/5 p-6 transition-colors hover:bg-white/10">
              <span className="flex size-11 items-center justify-center rounded-2xl bg-white/10 text-cyan"><i.icon className="size-5" /></span>
              <h3 className="mt-5 font-display text-lg font-semibold">{i.title}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-white/65">{i.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --------------------------------- Roles --------------------------------- */
const roles = [
  { id: "owner", name: "Owner", icon: BriefcaseBusiness, headline: "The whole organization at a glance", items: ["Spend, budgets and forecasts", "Project approvals with notes", "Org-wide security posture", "Trust Stars with history"], accent: "bg-tint-violet text-indigo" },
  { id: "hr", name: "HR", icon: Users, headline: "People operations without spreadsheets", items: ["ID verification review queue", "Payroll and leave review", "Onboarding and offboarding", "Directory and profiles"], accent: "bg-tint-mint text-[#008068]" },
  { id: "senior", name: "Senior developer", icon: Code2, headline: "Lead delivery and quality", items: ["Review junior proposals", "Team workload and tasks", "Repository health", "Security findings"], accent: "bg-tint-sky text-[#0b78b0]" },
  { id: "junior", name: "Junior developer", icon: Workflow, headline: "Focus on the next task", items: ["My tasks and pull requests", "Submit project proposals", "Findings assigned to me", "My Trust Stars"], accent: "bg-tint-amber text-[#a86500]" },
  { id: "analyst", name: "Security analyst", icon: ShieldCheck, headline: "Investigate with context", items: ["Attack-chain graph", "Incident response workflows", "Cloud risk inventory", "AI Copilot and simulations"], accent: "bg-tint-coral text-[#c21d45]" },
];

export function RolePreviews() {
  const [active, setActive] = React.useState(roles[0].id);
  const r = roles.find((x) => x.id === active)!;
  return (
    <section className="mx-auto max-w-7xl px-5 py-24 sm:px-8">
      <SectionHead title="A workspace for every role" body="Navigation, dashboards and permissions adapt to who is signed in." />
      <div className="mt-12 grid gap-6 lg:grid-cols-[320px_1fr]">
        <div role="tablist" aria-label="Roles" className="flex gap-2 overflow-x-auto lg:flex-col">
          {roles.map((x) => (
            <button key={x.id} role="tab" aria-selected={active === x.id} onClick={() => setActive(x.id)}
              className={cn("flex shrink-0 items-center gap-3 rounded-2xl border px-4 py-3.5 text-left transition-all", active === x.id ? "border-violet/40 bg-white shadow-card" : "border-transparent hover:bg-white/70")}>
              <span className={cn("flex size-10 items-center justify-center rounded-xl", x.accent)}><x.icon className="size-5" /></span>
              <span className="font-display text-[15px] font-semibold whitespace-nowrap">{x.name}</span>
            </button>
          ))}
        </div>
        <div role="tabpanel" className="card p-7 sm:p-9">
          <span className={cn("inline-flex size-12 items-center justify-center rounded-2xl", r.accent)}><r.icon className="size-6" /></span>
          <h3 className="mt-5 font-display text-2xl font-bold">{r.headline}</h3>
          <ul className="mt-6 grid gap-3 sm:grid-cols-2">
            {r.items.map((i) => (
              <li key={i} className="flex items-center gap-3 rounded-xl bg-canvas px-4 py-3.5 text-[15px] font-medium"><Check className="size-4 text-mint" />{i}</li>
            ))}
          </ul>
          <Button asChild variant="soft" className="mt-7"><Link href="/owner">Preview this workspace <ArrowRight /></Link></Button>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------ Live analytics ------------------------------ */
export function AnalyticsPreview() {
  const [rows, setRows] = React.useState(() => Array.from({ length: 24 }, (_, i) => ({ t: i, v: 48 + Math.sin(i / 3) * 12 + (i % 5) * 2 })));
  React.useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => {
      setRows((r) => {
        const last = r[r.length - 1];
        return [...r.slice(1), { t: last.t + 1, v: Math.max(30, Math.min(90, last.v + (Math.random() - 0.48) * 10)) }];
      });
    }, 1200);
    return () => clearInterval(id);
  }, []);
  const latest = rows[rows.length - 1].v;
  return (
    <section className="bg-white py-24">
      <div className="mx-auto grid max-w-7xl items-center gap-12 px-5 sm:px-8 lg:grid-cols-[1.1fr_1fr]">
        <div className="card overflow-hidden p-6">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-ink-2">API requests per minute</p>
              <p className="mt-1 font-display text-4xl font-extrabold tabular-nums">{Math.round(latest * 4)}</p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-tint-mint px-2.5 py-1 text-xs font-medium text-[#008068]"><span className="size-1.5 animate-pulse rounded-full bg-mint" /> Sample data</span>
          </div>
          <div className="mt-4 h-56" role="img" aria-label="Animated line chart of sample API traffic">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={rows} margin={{ left: -30, right: 0 }}>
                <defs><linearGradient id="liveFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors.cyan} stopOpacity={0.55} /><stop offset="100%" stopColor={colors.cyan} stopOpacity={0} /></linearGradient></defs>
                <XAxis dataKey="t" hide />
                <YAxis {...axisProps} domain={[20, 100]} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="v" name="Requests" stroke={colors.sky} strokeWidth={3} fill="url(#liveFill)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div>
          <SectionHead align="left" title="Spot the unusual, then investigate" body="Baselines for logins, devices, APIs and downloads make deviations easy to see. An unusual pattern is a reason to look closer, never a verdict on a person." />
          <ul className="mt-6 space-y-3 text-[15px] text-ink-2">
            {["Per-identity baselines that learn what normal looks like", "Anomalies grouped into incidents instead of alert floods", "Every flag links to the evidence behind it"].map((t) => (
              <li key={t} className="flex gap-3"><Check className="mt-1 size-4 shrink-0 text-mint" />{t}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* --------------------------------- Features --------------------------------- */
export function FeatureHighlights() {
  const f = [
    { icon: Wallet, t: "Cloud cost clarity", b: "AWS, Azure and GCP in one view, by department." },
    { icon: Network, t: "Attack-chain graph", b: "Connect scattered alerts into a story with timestamps." },
    { icon: Bell, t: "One notification center", b: "Approvals, incidents and reviews in a single inbox." },
    { icon: Workflow, t: "Guided lifecycles", b: "Onboard and offboard with a reversible access preview." },
    { icon: ScanSearch, t: "Four scanners, one list", b: "Semgrep, Bandit, Gitleaks and OSV findings together." },
    { icon: KeyRound, t: "Command palette", b: "Press Ctrl K to jump anywhere or run an action." },
  ];
  return (
    <section className="mx-auto max-w-7xl px-5 py-24 sm:px-8">
      <SectionHead title="Details that make the daily work easier" body="The small things are where a product earns its place on your team’s screen." />
      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {f.map((x) => (
          <div key={x.t} className="rounded-2xl border border-line bg-white p-5 transition-colors hover:border-violet/30">
            <span className="flex size-10 items-center justify-center rounded-xl bg-tint-violet text-indigo"><x.icon className="size-5" /></span>
            <p className="mt-4 font-display font-semibold">{x.t}</p>
            <p className="mt-1 text-sm text-ink-2">{x.b}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------ FAQ ------------------------------------ */
const faqs = [
  ["Is this connected to real systems?", "No. This is a front-end prototype running on seeded mock data. Verification, scans and AI responses are simulated and labeled as such."],
  ["How does website verification work?", "You add a generated TXT record to your DNS or publish a file on your site. In production, MESH would look it up. In this prototype the check is simulated."],
  ["Can MESH scan my repositories?", "Only with explicit authorization. The interface shows the consent state and confirms cleanup of temporary clones. Detected secrets are always redacted."],
  ["What are Trust Stars?", "A contextual signal built from reviewed events, with visible history. They support decisions made by people and never judge trustworthiness on their own."],
  ["Does VADER accuse employees?", "No. Unusual behavior is shown as a signal that needs investigation. It is not evidence of malicious intent."],
  ["Which roles are supported?", "Owner, HR, Senior Developer, Junior Developer and Security Analyst, each with tailored navigation and dashboards."],
];

export function Faq() {
  return (
    <section id="faq" className="mx-auto max-w-3xl scroll-mt-20 px-5 py-24 sm:px-8">
      <SectionHead title="Questions, answered" body="Short answers to what teams ask first." />
      <div className="mt-10 divide-y divide-line rounded-3xl border border-line bg-white">
        {faqs.map(([q, a]) => (
          <details key={q} className="group px-6 py-5 [&_summary::-webkit-details-marker]:hidden">
            <summary className="flex cursor-pointer items-center justify-between gap-4 font-display text-[16px] font-semibold">
              {q}
              <Plus className="size-5 shrink-0 text-ink-3 transition-transform group-open:rotate-45" />
            </summary>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-2">{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section className="px-5 pb-24 sm:px-8">
      <div className="gradient-violet relative mx-auto max-w-7xl overflow-hidden rounded-[32px] px-8 py-16 text-center text-white sm:py-20">
        <div className="pointer-events-none absolute -left-10 -top-10 size-64 rounded-full bg-white/15 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 right-0 size-72 rounded-full bg-cyan/40 blur-3xl" />
        <h2 className="relative font-display text-3xl font-extrabold sm:text-5xl">See the whole picture</h2>
        <p className="relative mx-auto mt-4 max-w-xl text-lg text-white/85">Set up an organization or walk through the demo workspace. No credit card, and nothing leaves your browser.</p>
        <div className="relative mt-8 flex flex-wrap justify-center gap-3">
          <Button size="lg" asChild className="bg-white !text-indigo hover:bg-white/90"><Link href="/register">Get Started</Link></Button>
          <Button size="lg" asChild variant="ghost" className="border border-white/40 !text-white hover:!bg-white/15"><Link href="/owner">Explore MESH</Link></Button>
        </div>
      </div>
    </section>
  );
}
