"use client";
import * as React from "react";
import { cn } from "@/lib/utils/cn";

export function OtpInput({ value, onChange, length = 6, invalid }: { value: string; onChange: (v: string) => void; length?: number; invalid?: boolean }) {
  const refs = React.useRef<(HTMLInputElement | null)[]>([]);
  const chars = Array.from({ length }, (_, i) => value[i] ?? "");

  function set(i: number, c: string) {
    const next = chars.slice();
    next[i] = c;
    onChange(next.join(""));
  }

  return (
    <div className="flex gap-2.5" role="group" aria-label="One-time code">
      {chars.map((c, i) => (
        <input
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          maxLength={1}
          value={c}
          aria-label={`Digit ${i + 1}`}
          aria-invalid={invalid}
          onChange={(e) => {
            const d = e.target.value.replace(/\D/g, "").slice(-1);
            set(i, d);
            if (d && i < length - 1) refs.current[i + 1]?.focus();
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace" && !chars[i] && i > 0) refs.current[i - 1]?.focus();
            if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
            if (e.key === "ArrowRight" && i < length - 1) refs.current[i + 1]?.focus();
          }}
          onPaste={(e) => {
            const t = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
            if (t) {
              e.preventDefault();
              onChange(t);
              refs.current[Math.min(t.length, length - 1)]?.focus();
            }
          }}
          className={cn(
            "h-14 w-full min-w-0 rounded-xl border bg-white text-center font-display text-xl font-bold text-ink transition-shadow focus:border-violet focus:outline-none focus:ring-4 focus:ring-violet/15",
            invalid ? "border-coral" : "border-line-strong"
          )}
        />
      ))}
    </div>
  );
}
