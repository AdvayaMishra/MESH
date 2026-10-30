import { cn } from "@/lib/utils/cn";
import { accentStyles, type Accent } from "@/lib/design-tokens";
import type { LucideIcon } from "lucide-react";

export function IconTile({ icon: Icon, accent, className }: { icon: LucideIcon; accent: Accent; className?: string }) {
  const a = accentStyles[accent];
  return (
    <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-xl", a.tint, a.text, className)}>
      <Icon className="size-[18px]" />
    </span>
  );
}

/** Renders whole stars for a 0–50 Trust score: floor(score / 10), no partial or half stars. */
export function TrustStars({ score, size = 14 }: { score: number; size?: number }) {
  const points = Math.max(0, Math.min(50, Math.round(score)));
  const stars = Math.floor(points / 10);
  return (
    <span className="inline-flex items-center gap-0.5" role="img" aria-label={`Trust Stars: ${points} of 50 points, ${stars} of 5 stars`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <svg key={i} width={size} height={size} viewBox="0 0 24 24" aria-hidden>
          <path
            d="M12 2.5l2.9 6.1 6.6.9-4.8 4.6 1.2 6.6L12 17.5 6.1 20.7l1.2-6.6L2.5 9.5l6.6-.9L12 2.5z"
            fill={i < stars ? "#FFB547" : "#E6EAF5"}
          />
        </svg>
      ))}
    </span>
  );
}
