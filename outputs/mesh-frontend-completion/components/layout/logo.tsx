import { cn } from "@/lib/utils/cn";

export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-hidden>
      <defs>
        <linearGradient id="lm-a" x1="4" y1="4" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop stopColor="#635BFF" />
          <stop offset="1" stopColor="#A78BFA" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#lm-a)" />
      <path d="M10 28V13.5L20 22l10-8.5V28" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="20" cy="22" r="2.4" fill="#67E8F9" />
      <circle cx="10" cy="13.5" r="1.8" fill="#fff" />
      <circle cx="30" cy="13.5" r="1.8" fill="#fff" />
    </svg>
  );
}

export function Logo({ className, collapsed }: { className?: string; collapsed?: boolean }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      {!collapsed && <span className="font-display text-xl font-extrabold tracking-tight text-ink">MESH</span>}
    </span>
  );
}
