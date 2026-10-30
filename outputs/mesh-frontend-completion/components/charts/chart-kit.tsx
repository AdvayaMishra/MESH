"use client";
import * as React from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils/cn";

/** Shared tooltip for Recharts. */
export function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: readonly { name?: string | number; value?: number | string; color?: string; dataKey?: string | number }[];
  label?: string | number;
  formatter?: (v: number, name: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-32 rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-pop">
      {label !== undefined && <p className="mb-1 font-medium text-ink">{label}</p>}
      <ul className="space-y-0.5">
        {payload.map((p) => (
          <li key={String(p.dataKey ?? p.name)} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-ink-2">
              <span className="size-2 rounded-full" style={{ background: p.color }} />
              {p.name}
            </span>
            <span className="font-medium text-ink">
              {typeof p.value === "number" && formatter ? formatter(p.value, String(p.name)) : p.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sparkline({ data, color = "#635BFF", height = 36 }: { data: number[]; color?: string; height?: number }) {
  const id = React.useId().replace(/:/g, "");
  const rows = data.map((v, i) => ({ i, v }));
  return (
    <div style={{ height }} aria-hidden className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`sp-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#sp-${id})`} isAnimationActive />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Semi-circular score gauge drawn in SVG. */
export function ScoreGauge({
  value,
  size = 200,
  label,
  color,
  caption,
}: {
  value: number;
  size?: number;
  label?: string;
  color?: string;
  caption?: string;
}) {
  const r = size / 2 - 16;
  const cx = size / 2;
  const cy = size / 2;
  const circ = Math.PI * r;
  const pct = Math.max(0, Math.min(100, value)) / 100;
  const stroke = color ?? (value >= 75 ? "#00C9A7" : value >= 50 ? "#FFB547" : "#FF6B8A");
  const gid = React.useId().replace(/:/g, "");
  return (
    <div className="relative" style={{ width: size, height: size / 2 + 28 }}>
      <svg width={size} height={size / 2 + 12} viewBox={`0 0 ${size} ${size / 2 + 12}`} role="img" aria-label={`${label ?? "Score"} ${value} out of 100`}>
        <defs>
          <linearGradient id={`g-${gid}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.55} />
            <stop offset="100%" stopColor={stroke} />
          </linearGradient>
        </defs>
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="#EEF1FA" strokeWidth={14} strokeLinecap="round" />
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke={`url(#g-${gid})`}
          strokeWidth={14}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - pct)}
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(.2,.8,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="font-display text-3xl font-bold leading-none text-ink">{Math.round(value)}</div>
        {caption && <div className="mt-1 text-xs text-ink-2">{caption}</div>}
      </div>
    </div>
  );
}

export function Legend({ items, className }: { items: { label: string; color: string; value?: string }[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2", className)}>
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[4px]" style={{ background: i.color }} />
          {i.label}
          {i.value && <span className="font-medium text-ink">{i.value}</span>}
        </li>
      ))}
    </ul>
  );
}

export const axisProps = {
  tick: { fill: "#94A3B8", fontSize: 12 },
  axisLine: false as const,
  tickLine: false as const,
};
