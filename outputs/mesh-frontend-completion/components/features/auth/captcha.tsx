"use client";
import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils/cn";

/** Integration point for hCaptcha or Cloudflare Turnstile. This placeholder performs no bot detection. */
export function CaptchaPlaceholder({ checked, onChange, error }: { checked: boolean; onChange: (v: boolean) => void; error?: string }) {
  return (
    <div>
      <label className={cn("flex cursor-pointer items-center gap-3 rounded-xl border bg-canvas px-4 py-3.5 transition-colors hover:border-violet/40", error ? "border-coral" : "border-line-strong")}>
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-5 rounded accent-violet" />
        <span className="flex-1 text-sm font-medium text-ink">I&apos;m not a robot</span>
        <span className="flex flex-col items-center text-[10px] text-ink-3"><ShieldCheck className="size-5 text-ink-3" />CAPTCHA</span>
      </label>
      <p className="mt-1.5 text-xs text-ink-3">Placeholder. A production build would mount hCaptcha or Turnstile here.</p>
      {error && <p role="alert" className="mt-1 text-xs text-[#d6294f]">{error}</p>}
    </div>
  );
}
