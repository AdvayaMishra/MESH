"use client";
import * as React from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, type LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Sparkline } from "@/components/charts/chart-kit";
import { useCountUp } from "@/hooks/use-count-up";
import { accentStyles, type Accent } from "@/lib/design-tokens";
import { cn } from "@/lib/utils/cn";

export function KpiCard({
  label,
  value,
  format,
  delta,
  deltaLabel = "vs last month",
  goodWhen = "up",
  icon: Icon,
  accent,
  spark,
  variant = "plain",
  suffix,
  href,
}: {
  label: string;
  value: number;
  format?: (n: number) => string;
  delta?: number;
  deltaLabel?: string;
  goodWhen?: "up" | "down";
  icon: LucideIcon;
  accent: Accent;
  spark?: number[];
  /** "gradient" fills the card with the accent for the one hero KPI. */
  variant?: "plain" | "gradient";
  suffix?: string;
  href?: string;
}) {
  const v = useCountUp(Number.isFinite(value)?value:0);
  const a = accentStyles[accent];
  const up = (delta ?? 0) >= 0;
  const good = goodWhen === "up" ? up : !up;
  const hero = variant === "gradient";
  const body = (
    <Card
      hover
      className={cn(
        "relative h-full overflow-hidden p-5",
        hero && "border-transparent text-white",
        hero && accent === "violet" && "gradient-violet",
        hero && accent === "mint" && "gradient-mint",
        hero && accent === "sky" && "gradient-cyan",
        hero && accent === "coral" && "gradient-coral"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={cn("text-[13px] font-medium", hero ? "text-white/85" : "text-ink-2")}>{label}</p>
          <p className={cn("mt-2 font-display text-[28px] font-bold leading-none tabular-nums", hero ? "text-white" : "text-ink")}>
            {!Number.isFinite(value)?"Unavailable":format ? format(v) : Math.round(v).toLocaleString("en-US")}
            {suffix && Number.isFinite(value) && <span className={cn("ml-1 text-base font-semibold", hero ? "text-white/80" : "text-ink-3")}>{suffix}</span>}
          </p>
        </div>
        <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-xl", hero ? "bg-white/20 text-white" : cn(a.tint, a.text))}>
          <Icon className="size-5" />
        </span>
      </div>
      {delta !== undefined && Number.isFinite(delta) && (
        <p className="mt-3 flex items-center gap-1.5 text-xs">
          <span
            className={cn(
              "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-semibold",
              hero ? "bg-white/20 text-white" : good ? "bg-tint-mint text-[#008068]" : "bg-tint-coral text-[#c21d45]"
            )}
          >
            {up ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
            {Math.abs(delta)}
            {Math.abs(delta) % 1 !== 0 || delta === 0 ? "%" : ""}
          </span>
          <span className={hero ? "text-white/80" : "text-ink-3"}>{deltaLabel}</span>
        </p>
      )}
      {spark && (
        <div className="-mx-1 mt-2">
          <Sparkline data={spark} color={hero ? "#ffffff" : a.hex} />
        </div>
      )}
    </Card>
  );
  return href ? (
    <Link href={href} className="block h-full rounded-[18px]">
      {body}
    </Link>
  ) : (
    body
  );
}
