"use client";
import * as React from "react";
import { Building2, CalendarDays, MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { greeting } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

export function WelcomeHero() {
  const { currentUser, org } = useDataset();
  // Computed after mount so server and client markup match.
  const [hello, setHello] = React.useState("Welcome back");
  const [today, setToday] = React.useState("");
  React.useEffect(() => {
    const raf = requestAnimationFrame(() => {
      const d = new Date();
      setHello(greeting(d));
      setToday(d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }));
    });
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <section className="relative overflow-hidden rounded-[24px] border border-violet/15 bg-gradient-to-br from-[#efecff] via-[#f6f4ff] to-[#e9f7ff] p-6 sm:p-8">
      <svg className="pointer-events-none absolute -right-8 top-0 h-full w-[420px] opacity-70" viewBox="0 0 420 220" fill="none" aria-hidden>
        <g stroke="#635BFF" strokeOpacity="0.25" strokeWidth="1.5">
          <path d="M40 150 L140 70 L250 120 L350 40" className="flow-line" />
          <path d="M140 70 L180 190 L300 170 L350 40" />
          <path d="M250 120 L300 170" />
        </g>
        {[[40,150,"#00C9A7"],[140,70,"#635BFF"],[250,120,"#38BDF8"],[350,40,"#FF6B8A"],[180,190,"#A78BFA"],[300,170,"#FFB547"]].map(([x,y,c]) => (
          <g key={`${x}-${y}`}>
            <circle cx={x as number} cy={y as number} r="14" fill={c as string} fillOpacity="0.15" />
            <circle cx={x as number} cy={y as number} r="6" fill={c as string} />
          </g>
        ))}
      </svg>
      <div className="relative max-w-xl">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="violet"><Building2 className="size-3" /> {org.name}</Badge>
          <Badge tone="neutral"><MapPin className="size-3" /> {org.region}</Badge>
          {today && <Badge tone="neutral"><CalendarDays className="size-3" /> {today}</Badge>}
        </div>
        <h1 className="mt-4 font-display text-3xl font-extrabold text-ink sm:text-4xl">
          {hello}, {currentUser.name.split(" ")[0]} 👋
        </h1>
        <p className="mt-2 text-[15px] text-ink-2">Here&apos;s what&apos;s happening across your organization today.</p>
      </div>
    </section>
  );
}
