"use client";
import Link from "next/link";
import { ArrowRight, Play, ShieldCheck, TrendingUp } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Sparkline } from "@/components/charts/chart-kit";
import { ScoreGauge } from "@/components/charts/chart-kit";
import { Avatar } from "@/components/ui/avatar";

const nodes = [
  { id: "owner", x: 120, y: 90, color: "#635BFF", label: "Owner" },
  { id: "people", x: 400, y: 70, color: "#00C9A7", label: "People" },
  { id: "dev", x: 90, y: 330, color: "#38BDF8", label: "DevTrack" },
  { id: "vader", x: 420, y: 340, color: "#FF6B8A", label: "VADER" },
];

function NetworkViz() {
  const cx = 260;
  const cy = 210;
  return (
    <svg viewBox="0 0 520 420" className="absolute inset-0 h-full w-full" fill="none" aria-hidden>
      <defs>
        <radialGradient id="core" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#635BFF" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#635BFF" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r="130" fill="url(#core)" />
      {[70, 120, 175].map((r) => (
        <circle key={r} cx={cx} cy={cy} r={r} stroke="#635BFF" strokeOpacity="0.1" strokeDasharray="2 6" />
      ))}
      {nodes.map((n) => (
        <g key={n.id}>
          <line x1={cx} y1={cy} x2={n.x} y2={n.y} stroke={n.color} strokeOpacity="0.5" strokeWidth="2" className="flow-line" />
          <circle cx={n.x} cy={n.y} r="26" fill={n.color} fillOpacity="0.14" />
          <circle cx={n.x} cy={n.y} r="9" fill={n.color} />
        </g>
      ))}
      <circle cx={cx} cy={cy} r="34" fill="#fff" stroke="#635BFF" strokeOpacity="0.25" strokeWidth="2" />
      <text x={cx} y={cy + 5} textAnchor="middle" fontSize="15" fontWeight="800" fill="#4F46E5" fontFamily="var(--font-display)">MESH</text>
    </svg>
  );
}

export function Hero() {
  const reduce = useReducedMotion();
  const fade = (d: number) => (reduce ? {} : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay: d, ease: [0.22, 1, 0.36, 1] as const } });
  return (
    <section className="gradient-hero relative overflow-hidden pt-28 sm:pt-32">
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-canvas" />
      <div className="dot-grid pointer-events-none absolute inset-0 opacity-40 [mask-image:radial-gradient(70%_60%_at_50%_30%,black,transparent)]" />
      <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 pb-20 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:pb-28">
        <div>
          <motion.a {...fade(0)} href="#modules" className="inline-flex items-center gap-2 rounded-full border border-violet/20 bg-white/80 px-3 py-1.5 text-[13px] font-medium text-indigo shadow-sm backdrop-blur">
            <span className="rounded-full gradient-violet px-2 py-0.5 text-[11px] font-semibold text-white">New</span>
            VADER attack-chain correlation is here
            <ArrowRight className="size-3.5" />
          </motion.a>
          <motion.h1 {...fade(0.08)} className="mt-6 font-display text-[44px] font-extrabold leading-[1.02] text-ink sm:text-6xl xl:text-[72px]">
            One Platform.
            <br />
            Every Team.
            <br />
            <span className="bg-gradient-to-r from-[#635BFF] via-[#8B7BFF] to-[#38BDF8] bg-clip-text text-transparent">Total Visibility.</span>
          </motion.h1>
          <motion.p {...fade(0.16)} className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">
            Bring your people, projects, operations, and cybersecurity together in one intelligent workspace.
          </motion.p>
          <motion.div {...fade(0.24)} className="mt-8 flex flex-wrap items-center gap-3">
            <Button variant="gradient" size="lg" asChild>
              <Link href="/register">Get Started <ArrowRight /></Link>
            </Button>
            <Button variant="secondary" size="lg" asChild>
              <Link href="/owner"><Play className="fill-current" /> Explore MESH</Link>
            </Button>
          </motion.div>
          <motion.div {...fade(0.32)} className="mt-8 flex items-center gap-4">
            <div className="flex -space-x-2">
              {["Priya Raghunathan", "Daniel Okafor", "Nadia Farouk", "Sofia Lindqvist"].map((n) => <Avatar key={n} name={n} size={34} />)}
            </div>
            <p className="text-sm text-ink-2">Prototype workspace with 24 seeded teammates.<br className="hidden sm:block" /> No sign-up needed to explore.</p>
          </motion.div>
        </div>

        {/* Visual composition */}
        <div className="relative mx-auto h-[460px] w-full max-w-[560px] sm:h-[520px]">
          <NetworkViz />

          <div className="float-slow absolute left-0 top-6 w-52 rotate-[-4deg] rounded-2xl border border-white bg-white/90 p-4 shadow-pop backdrop-blur">
            <p className="text-xs font-medium text-ink-2">Monthly cloud spend</p>
            <p className="mt-1 font-display text-2xl font-bold">$123.7k</p>
            <p className="mt-1 flex items-center gap-1 text-xs font-medium text-[#008068]"><TrendingUp className="size-3.5" /> forecast within budget</p>
            <Sparkline data={[98, 101, 105, 109, 114, 119, 124]} color="#635BFF" height={40} />
          </div>

          <div className="float-slower absolute right-0 top-0 w-56 rotate-[3deg] rounded-2xl border border-white bg-white/90 p-4 shadow-pop backdrop-blur">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-ink-2">Security posture</p>
              <ShieldCheck className="size-4 text-mint" />
            </div>
            <div className="mt-2 flex justify-center"><ScoreGauge value={82} size={150} caption="Strong" /></div>
          </div>

          <div className="float-slow absolute bottom-24 left-6 w-60 rounded-2xl border border-white bg-white/90 p-4 shadow-pop backdrop-blur sm:bottom-28">
            <p className="text-xs font-medium text-ink-2">Awaiting approval</p>
            <div className="mt-2 space-y-2">
              {[["Vista Predictive Maintenance", "High"], ["Keep Secrets Vault", "Critical"]].map(([n, p]) => (
                <div key={n} className="flex items-center justify-between gap-2 rounded-lg bg-canvas px-2.5 py-2">
                  <span className="truncate text-xs font-medium text-ink">{n}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${p === "Critical" ? "bg-tint-coral text-[#c21d45]" : "bg-tint-amber text-[#a86500]"}`}>{p}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="float-slower absolute bottom-2 right-2 w-64 rounded-2xl border border-white bg-white/90 p-4 shadow-pop backdrop-blur">
            <p className="text-xs font-medium text-ink-2">Attack chain · INC-3021</p>
            <div className="mt-3 flex items-center">
              {["#FFB547", "#FFB547", "#FF8A3D", "#FF8A3D", "#FF6B8A"].map((c, i, a) => (
                <div key={i} className="flex flex-1 items-center">
                  <span className="size-3.5 shrink-0 rounded-full ring-4" style={{ background: c, boxShadow: `0 0 0 4px ${c}33` }} />
                  {i < a.length - 1 && <span className="h-0.5 flex-1" style={{ background: `linear-gradient(90deg, ${c}, ${a[i + 1]})` }} />}
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-ink-2">Unusual login → API abuse → large download</p>
          </div>
        </div>
      </div>
    </section>
  );
}
