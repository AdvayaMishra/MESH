import { cn } from "@/lib/utils/cn";
import { type Accent, accentStyles } from "@/lib/design-tokens";

export function Progress({
  value,
  accent = "violet",
  className,
  label,
}: {
  value: number;
  accent?: Accent;
  className?: string;
  label?: string;
}) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={v}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-[#eef1fa]", className)}
    >
      <div
        className="h-full rounded-full transition-[width] duration-700 ease-out"
        style={{ width: `${v}%`, background: accentStyles[accent].hex }}
      />
    </div>
  );
}
