"use client";
import { isLive } from "@/lib/connected/live-state";
import { LiveWhatIf } from "@/lib/connected/finance";
import * as React from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowUp, Info, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { SimulatedTag } from "@/components/ui/badge";
import { ChartTooltip, Legend, axisProps } from "@/components/charts/chart-kit";
import { Skeleton } from "@/components/ui/skeleton";
import { useStreamText } from "@/hooks/use-stream-text";
import { api } from "@/lib/api";
import { colors } from "@/lib/design-tokens";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";
import { useTenant } from "@/stores/tenant-store";

type Result = Awaited<ReturnType<typeof api.whatIf>>;

const toneCls = {
  mint: "bg-tint-mint text-[#008068]",
  amber: "bg-tint-amber text-[#a86500]",
  coral: "bg-tint-coral text-[#c21d45]",
  violet: "bg-tint-violet text-indigo",
} as const;

function DemoWhatIfStudio() {
  const orgId = useTenant((s) => s.orgId);
  return <WhatIfSession key={orgId} />;
}

function WhatIfSession() {
  const { whatIfPrompts } = useDataset();
  const [prompt, setPrompt] = React.useState("");
  const [asked, setAsked] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<Result | null>(null);
  const { text, streaming, start, reset } = useStreamText();
  const [showChart, setShowChart] = React.useState(false);

  async function ask(q: string) {
    const question = q.trim();
    if (!question || loading) return;
    setPrompt(question);
    setAsked(question);
    setLoading(true);
    setResult(null);
    setShowChart(false);
    reset();
    const r = await api.whatIf(question);
    setLoading(false);
    setResult(r);
    const body = r.result
      ? `${r.result.headline}. ${r.result.summary}`
      : "Try a suggested scenario or a question such as “What if cloud spend decreases by 15%?” This demo supports percentage changes to total cloud spend; it cannot interpret every question.";
    start(body, () => setShowChart(true));
  }

  const scenario = result?.result;
  const isProjects = asked === "Which projects need additional resources?";

  return (
    <section
      aria-labelledby="whatif-title"
      className="relative overflow-hidden rounded-[22px] border border-violet/20 bg-gradient-to-br from-[#f4f2ff] via-white to-[#eefaff] p-5 shadow-card sm:p-6"
    >
      <div className="pointer-events-none absolute -right-16 -top-16 size-64 rounded-full bg-lavender/25 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-20 left-10 size-56 rounded-full bg-cyan/25 blur-3xl" />
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-xl gradient-violet text-white shadow-[0_8px_18px_-8px_rgba(99,91,255,0.9)]">
              <Sparkles className="size-5" />
            </span>
            <div>
              <h2 id="whatif-title" className="font-display text-lg font-bold text-ink">AI What-If Studio</h2>
              <p className="text-[13px] text-ink-2">Ask a planning question and see the projected impact.</p>
            </div>
          </div>
          <SimulatedTag label="Simulated analysis" />
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {whatIfPrompts.map((p) => (
            <button
              key={p}
              onClick={() => ask(p)}
              className={cn(
                "rounded-full border bg-white px-3.5 py-1.5 text-left text-[13px] transition-all hover:-translate-y-0.5 hover:border-violet/40 hover:text-indigo hover:shadow-sm",
                asked === p ? "border-violet text-indigo" : "border-line-strong text-ink-2"
              )}
            >
              {p}
            </button>
          ))}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(prompt);
          }}
          className="mt-4 flex items-center gap-2 rounded-2xl border border-line-strong bg-white p-1.5 pl-4 focus-within:border-violet focus-within:ring-4 focus-within:ring-violet/15"
        >
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            aria-label="Ask a what-if question"
            placeholder="e.g. What if cloud spend decreases by 15%?"
            className="h-10 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-3"
          />
          <Button type="submit" variant="gradient" size="icon" disabled={loading || !prompt.trim()} aria-label="Run analysis">
            <ArrowUp />
          </Button>
        </form>

        {(loading || asked) && (
          <div className="mt-5 rounded-2xl border border-line bg-white/80 p-4 sm:p-5" aria-live="polite">
            {loading ? (
              <div className="space-y-3">
                <p className="text-[13px] font-medium text-indigo">Analysing “{asked}”…</p>
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-4 w-3/5" />
                <Skeleton className="h-40 w-full" />
              </div>
            ) : (
              <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
                <div>
                  <p className={cn("text-[14.5px] leading-relaxed text-ink", streaming && "caret")}>{text}</p>
                  {scenario && showChart && (
                    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-4 grid grid-cols-2 gap-2.5">
                      {scenario.impact.map((m) => (
                        <div key={m.label} className={cn("rounded-xl px-3 py-2.5", toneCls[m.tone])}>
                          <p className="text-[11px] opacity-80">{m.label}</p>
                          <p className="font-display text-base font-bold">{m.value}</p>
                        </div>
                      ))}
                    </motion.div>
                  )}
                  {scenario && showChart && (
                    <div className="mt-4 rounded-xl border border-dashed border-line-strong bg-canvas p-3">
                      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink-2">
                        <Info className="size-3.5" /> Assumptions
                      </p>
                      <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink-2">
                        {scenario.assumptions.map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                {scenario && showChart && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-[13px] font-semibold text-ink">{isProjects ? "Progress at deadline (%)" : "Projected monthly spend"}</p>
                      <Legend items={[{ label: "Baseline", color: "#C9D2EA" }, { label: "Scenario", color: colors.violet }]} />
                    </div>
                    <div className="h-60 w-full" role="img" aria-label="Bar chart comparing baseline to scenario">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={scenario.series} margin={{ left: -14, right: 4, top: 8 }}>
                          <CartesianGrid vertical={false} stroke="#EEF1FA" />
                          <XAxis dataKey="label" {...axisProps} />
                          <YAxis {...axisProps} tickFormatter={(v: number) => (isProjects ? `${v}%` : `$${Math.round(v / 1000)}k`)} />
                          <Tooltip cursor={{ fill: "rgba(99,91,255,0.05)" }} content={<ChartTooltip formatter={(v) => (isProjects ? `${v}%` : `$${v.toLocaleString("en-US")}`)} />} />
                          <Bar dataKey="baseline" name="Baseline" fill="#C9D2EA" radius={[6, 6, 0, 0]} />
                          <Bar dataKey="scenario" name="Scenario" fill={colors.violet} radius={[6, 6, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <p className="mt-1 text-[11px] text-ink-3">Figures are modelled from mock data. They are not billing records.</p>
                  </motion.div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export function WhatIfStudio(){return isLive()?<LiveWhatIf/>:<DemoWhatIfStudio/>;}
