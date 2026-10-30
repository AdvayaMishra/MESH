const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** Compact formatting is hand-rolled because Intl compact output differs between Node and browsers (hydration mismatch). */
export const fmtCurrency = (n: number, compact = false, currency = "USD") => {
  if(!Number.isFinite(n))return "Not recorded";
  if(currency!=="USD")return new Intl.NumberFormat("en-US",{style:"currency",currency,maximumFractionDigits:2}).format(n);
  if (!compact) return usd.format(n);
  const abs = Math.abs(n);
  const trim = (v: number) => String(Math.round(v * 10) / 10);
  if (abs >= 1_000_000) return `$${trim(n / 1_000_000)}M`;
  if (abs >= 1_000) return `$${trim(n / 1_000)}K`;
  return `$${Math.round(n)}`;
};

export const fmtNumber = (n: number) => Number.isFinite(n)?new Intl.NumberFormat("en-US").format(n):"Not recorded";

export const fmtPercent = (n: number, digits = 0) => Number.isFinite(n)?`${n.toFixed(digits)}%`:"Not recorded";

export function fmtDate(iso: string, opts?: Intl.DateTimeFormatOptions) {
  if(!iso||!Number.isFinite(Date.parse(iso)))return "Not recorded";
  return new Date(iso).toLocaleDateString("en-US", opts ?? { month: "short", day: "numeric", year: "numeric" });
}

export function fmtTime(iso: string) {
  if(!iso||!Number.isFinite(Date.parse(iso)))return "Not recorded";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
}

/** Mock "now" keeps relative times deterministic across server and client renders. */
export const MOCK_NOW = new Date("2026-10-23T10:30:00Z");

export function timeAgo(iso: string, now: Date = new Date()) {
  if(!iso||!Number.isFinite(Date.parse(iso)))return "Not recorded";
  const diff = (now.getTime() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return fmtDate(iso, { month: "short", day: "numeric" });
}

export function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function greeting(date = new Date()) {
  const h = date.getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}
