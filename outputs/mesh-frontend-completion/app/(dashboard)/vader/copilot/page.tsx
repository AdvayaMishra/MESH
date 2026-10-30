"use client";
import * as React from "react";
import Link from "next/link";
import { ArrowUp, Bot, ChevronDown, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/features/page-header";
import { Button } from "@/components/ui/button";
import { SimulatedTag } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { useStreamText } from "@/hooks/use-stream-text";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";
import { useTenant } from "@/stores/tenant-store";
import { useWorkspace } from "@/stores/workspace-store";
import { COPILOT_PROMPTS as prompts, answerCopilotQuestion, type Answer } from "@/lib/copilot-answers";

type Msg = { role: "user" | "ai"; text: string; answer?: Answer; done?: boolean };

function AiBubble({ answer, onDone, animate }: { answer: Answer; onDone: () => void; animate: boolean }) {
  const { text, streaming, start } = useStreamText();
  const [shown, setShown] = React.useState(!animate);
  const [open, setOpen] = React.useState(false);
  const started = React.useRef(false);
  React.useEffect(() => {
    if (!animate || started.current) return;
    started.current = true;
    start(answer.text, () => { setShown(true); onDone(); });
  }, [animate, answer.text, start, onDone]);
  return (
    <div className="max-w-[92%] rounded-2xl rounded-tl-md border border-line bg-white p-4 shadow-sm sm:max-w-[85%]">
      <p className={cn("text-[14.5px] leading-relaxed text-ink", streaming && "caret")}>{animate ? text : answer.text}</p>
      {shown && (
        <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}>
          {answer.bullets && <ul className="mt-3 space-y-1.5 text-[13.5px] text-ink">{answer.bullets.map((b) => <li key={b} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-violet" />{b}</li>)}</ul>}
          {answer.refs.length > 0 && <div className="mt-3 flex flex-wrap items-center gap-1.5"><span className="text-xs text-ink-3">Evidence:</span>{answer.refs.map((r) => <Link key={r.label} href={r.href} className="rounded-full bg-tint-violet px-2.5 py-1 text-xs font-medium text-indigo hover:bg-[#e6e2ff]">{r.label}</Link>)}</div>}
          {answer.next && <p className="mt-3 rounded-xl bg-tint-mint px-3.5 py-2.5 text-[13px] text-[#065f4d]"><span className="font-semibold">Suggested next step:</span> {answer.next}</p>}
          {answer.details.length > 0 && (
            <div className="mt-3">
              <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-1 text-xs font-medium text-ink-2 hover:text-ink"><ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />Technical details</button>
              {open && <ul className="mt-2 space-y-1 rounded-xl bg-canvas p-3 font-mono text-[11.5px] text-ink-2">{answer.details.map((d) => <li key={d}>• {d}</li>)}</ul>}
            </div>
          )}
          <p className="mt-3 text-[11px] text-ink-3">Simulated response from seeded data. Verify evidence before acting.</p>
        </motion.div>
      )}
    </div>
  );
}

export default function CopilotPage() {
  const orgId = useTenant((s) => s.orgId);
  return <CopilotSession key={orgId} />;
}

function CopilotSession() {
  const { currentUser, riskComponents, riskTrend, cloudResources, attackChain } = useDataset();
  const incidents = useWorkspace((s) => s.incidents);
  const source = React.useMemo(() => ({ incidents, riskComponents, riskTrend, cloudResources, attackChain }), [incidents, riskComponents, riskTrend, cloudResources, attackChain]);
  const [msgs, setMsgs] = React.useState<Msg[]>([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);
  React.useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  function send(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    setInput("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text: question }]);
    timerRef.current = setTimeout(() => setMsgs((m) => [...m, { role: "ai", text: question, answer: answerCopilotQuestion(question, source) }]), 600);
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col" style={{ minHeight: "calc(100dvh - 8rem)" }}>
      <PageHeader title="VADER Copilot" description="Ask about incidents, risk and permissions. Answers cite the evidence they use." badge={<SimulatedTag label="Simulated AI" />} />
      <div className="card flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6" aria-live="polite">
          {msgs.length === 0 && (
            <div className="flex flex-col items-center py-10 text-center">
              <span className="flex size-14 items-center justify-center rounded-2xl gradient-violet text-white shadow-[0_10px_24px_-8px_rgba(99,91,255,0.8)]"><Sparkles className="size-7" /></span>
              <h2 className="mt-4 font-display text-xl font-bold">What would you like to investigate?</h2>
              <p className="mt-1 max-w-md text-sm text-ink-2">Ask a question in your own words or start with a suggestion. Answers are grounded in the active organization’s seeded demo data.</p>
              <div className="mt-6 flex max-w-2xl flex-wrap justify-center gap-2">{prompts.map((p) => <button key={p} onClick={() => send(p)} className="rounded-full border border-line-strong bg-white px-4 py-2 text-[13px] text-ink-2 transition-all hover:-translate-y-0.5 hover:border-violet/40 hover:text-indigo hover:shadow-sm">{p}</button>)}</div>
            </div>
          )}
          {msgs.map((m, i) => m.role === "user" ? (
            <div key={i} className="flex items-start justify-end gap-3"><div className="max-w-[85%] rounded-2xl rounded-tr-md bg-violet px-4 py-2.5 text-[14.5px] text-white">{m.text}</div><Avatar name={currentUser.name} size={32} /></div>
          ) : (
            <div key={i} className="flex items-start gap-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-full gradient-violet text-white"><Bot className="size-4" /></span><AiBubble answer={m.answer!} animate={i === msgs.length - 1} onDone={() => setBusy(false)} /></div>
          ))}
          {busy && msgs[msgs.length - 1]?.role === "user" && <div className="flex items-center gap-3"><span className="flex size-8 items-center justify-center rounded-full gradient-violet text-white"><Bot className="size-4" /></span><span className="flex gap-1" aria-label="Copilot is thinking">{[0, 1, 2].map((d) => <span key={d} className="size-2 animate-bounce rounded-full bg-lavender" style={{ animationDelay: `${d * 120}ms` }} />)}</span></div>}
          <div ref={endRef} />
        </div>
        {msgs.length > 0 && <div className="flex gap-2 overflow-x-auto border-t border-line px-4 py-2.5 no-scrollbar">{prompts.filter((p) => !msgs.some((m) => m.text === p)).slice(0, 3).map((p) => <button key={p} onClick={() => send(p)} disabled={busy} className="shrink-0 rounded-full bg-tint-violet px-3 py-1.5 text-xs font-medium text-indigo disabled:opacity-50">{p}</button>)}</div>}
        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex items-center gap-2 border-t border-line p-3">
          <input value={input} onChange={(e) => setInput(e.target.value)} aria-label="Ask the Copilot" placeholder="Ask about an incident, resource or risk…" className="h-11 flex-1 rounded-xl border border-line-strong bg-white px-4 text-sm placeholder:text-ink-3 focus:border-violet focus:outline-none focus:ring-4 focus:ring-violet/15" />
          <Button type="submit" variant="gradient" size="icon" disabled={busy || !input.trim()} aria-label="Send"><ArrowUp /></Button>
        </form>
      </div>
    </div>
  );
}
