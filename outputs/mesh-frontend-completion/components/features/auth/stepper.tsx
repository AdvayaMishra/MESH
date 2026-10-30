import { Check } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export interface Step {
  label: string;
}

export function Stepper({ steps, current, className }: { steps: Step[]; current: number; className?: string }) {
  return (
    <ol className={cn("flex items-center", className)} aria-label="Progress">
      {steps.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s.label} className={cn("flex items-center", i < steps.length - 1 && "flex-1")} aria-current={active ? "step" : undefined}>
            <span className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors",
                  done && "bg-mint text-[#04332b]",
                  active && "gradient-violet text-white shadow-[0_6px_14px_-4px_rgba(99,91,255,0.7)]",
                  !done && !active && "bg-[#eef1fa] text-ink-3"
                )}
              >
                {done ? <Check className="size-3.5" /> : i + 1}
              </span>
              <span className={cn("hidden text-[13px] font-medium sm:block", active ? "text-ink" : "text-ink-3")}>{s.label}</span>
            </span>
            {i < steps.length - 1 && <span className={cn("mx-3 h-0.5 flex-1 rounded-full", done ? "bg-mint" : "bg-[#e6eaf5]")} />}
          </li>
        );
      })}
    </ol>
  );
}

export const ownerSteps: Step[] = [{ label: "Account" }, { label: "Email" }, { label: "Organization" }, { label: "Domain" }, { label: "Review" }];
export const employeeSteps: Step[] = [{ label: "Invitation" }, { label: "Upload ID" }, { label: "Review" }, { label: "Activate" }];
