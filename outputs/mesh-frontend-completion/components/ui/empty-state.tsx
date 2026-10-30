import { cn } from "@/lib/utils/cn";

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      <svg width="132" height="104" viewBox="0 0 132 104" fill="none" aria-hidden>
        <ellipse cx="66" cy="94" rx="46" ry="6" fill="#EEF1FA" />
        <rect x="22" y="18" width="88" height="62" rx="14" fill="#F1EFFF" />
        <rect x="32" y="30" width="40" height="7" rx="3.5" fill="#C9C4FF" />
        <rect x="32" y="44" width="68" height="6" rx="3" fill="#E1DEFF" />
        <rect x="32" y="56" width="52" height="6" rx="3" fill="#E1DEFF" />
        <circle cx="102" cy="70" r="15" fill="#fff" stroke="#635BFF" strokeWidth="2.5" />
        <path d="M96.5 70.5l4 4 7-8" stroke="#00C9A7" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="26" cy="22" r="4" fill="#67E8F9" />
        <circle cx="116" cy="26" r="3" fill="#FFB547" />
      </svg>
      <h4 className="mt-4 font-display text-base font-semibold text-ink">{title}</h4>
      {description && <p className="mt-1 max-w-sm text-sm text-ink-2">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
