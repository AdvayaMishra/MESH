"use client";
import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils/cn";

export const PasswordField = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => {
  const [show, setShow] = React.useState(false);
  return (
    <div className="relative">
      <Input ref={ref} type={show ? "text" : "password"} className={cn("pr-11", className)} {...props} />
      <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-ink-3 hover:text-ink">
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
});
PasswordField.displayName = "PasswordField";

export function passwordScore(pw: string) {
  let s = 0;
  if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return s;
}

export function PasswordMeter({ value }: { value: string }) {
  const s = passwordScore(value);
  const labels = ["Too weak", "Weak", "Fair", "Good", "Strong"];
  const colorsArr = ["#E6EAF5", "#FF6B8A", "#FFB547", "#38BDF8", "#00C9A7"];
  return (
    <div aria-live="polite" className="mt-2">
      <div className="flex gap-1.5">
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className="h-1.5 flex-1 rounded-full transition-colors" style={{ background: i <= s ? colorsArr[s] : "#E6EAF5" }} />
        ))}
      </div>
      {value && <p className="mt-1 text-xs text-ink-2">{labels[s]}. Use 10+ characters with mixed case, a number and a symbol.</p>}
    </div>
  );
}
