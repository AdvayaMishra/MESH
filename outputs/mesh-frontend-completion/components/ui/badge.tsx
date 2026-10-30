import { cn } from "@/lib/utils/cn";
import { severityStyles, type Severity } from "@/lib/design-tokens";

type Tone = "violet" | "mint" | "sky" | "amber" | "coral" | "neutral" | "indigo";

const tones: Record<Tone, string> = {
  violet: "bg-tint-violet text-indigo",
  indigo: "bg-[#e8e7ff] text-indigo",
  mint: "bg-tint-mint text-[#008068]",
  sky: "bg-tint-sky text-[#0b78b0]",
  amber: "bg-tint-amber text-[#a86500]",
  coral: "bg-tint-coral text-[#c21d45]",
  neutral: "bg-[#eef1fa] text-ink-2",
};

export function Badge({
  tone = "neutral",
  dot,
  className,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        tones[tone],
        className
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const s = severityStyles[severity];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        s.bg,
        s.text,
        className
      )}
    >
      <span className={cn("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

/** Marks data that comes from mock/simulated sources so it is never mistaken for real results. */
export function SimulatedTag({ className, label = "Simulated" }: { className?: string; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-dashed border-amber/60 bg-tint-amber px-2 py-0.5 text-[11px] font-medium text-[#a86500]",
        className
      )}
      title="This result is generated from mock data. No real system was contacted."
    >
      <span className="size-1.5 rounded-full bg-amber" />
      {label}
    </span>
  );
}
