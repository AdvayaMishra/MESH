/** Centralized design tokens, mirrored from globals.css for use in charts and SVG. */
export const colors = {
  violet: "#635BFF",
  indigo: "#4F46E5",
  mint: "#00C9A7",
  sky: "#38BDF8",
  cyan: "#67E8F9",
  amber: "#FFB547",
  coral: "#FF6B8A",
  lavender: "#A78BFA",
  ink: "#172033",
  ink2: "#64748B",
  ink3: "#94A3B8",
  line: "#E6EAF5",
  canvas: "#F8FAFF",
} as const;

export type Accent = "violet" | "mint" | "sky" | "amber" | "coral" | "cyan" | "indigo";

export const accentStyles: Record<Accent, { text: string; bg: string; tint: string; ring: string; hex: string }> = {
  violet: { text: "text-violet", bg: "bg-violet", tint: "bg-tint-violet", ring: "ring-violet/20", hex: colors.violet },
  indigo: { text: "text-indigo", bg: "bg-indigo", tint: "bg-tint-violet", ring: "ring-indigo/20", hex: colors.indigo },
  mint: { text: "text-[#00977d]", bg: "bg-mint", tint: "bg-tint-mint", ring: "ring-mint/25", hex: colors.mint },
  sky: { text: "text-[#0b86c4]", bg: "bg-sky", tint: "bg-tint-sky", ring: "ring-sky/25", hex: colors.sky },
  cyan: { text: "text-[#0e9db5]", bg: "bg-cyan", tint: "bg-tint-sky", ring: "ring-cyan/30", hex: colors.cyan },
  amber: { text: "text-[#b87400]", bg: "bg-amber", tint: "bg-tint-amber", ring: "ring-amber/30", hex: colors.amber },
  coral: { text: "text-[#d6294f]", bg: "bg-coral", tint: "bg-tint-coral", ring: "ring-coral/25", hex: colors.coral },
};

export const severityStyles = {
  critical: { label: "Critical", text: "text-[#c21d45]", bg: "bg-tint-coral", dot: "bg-coral", hex: colors.coral },
  high: { label: "High", text: "text-[#c25a00]", bg: "bg-[#fff1e3]", dot: "bg-[#ff8a3d]", hex: "#FF8A3D" },
  medium: { label: "Medium", text: "text-[#b87400]", bg: "bg-tint-amber", dot: "bg-amber", hex: colors.amber },
  low: { label: "Low", text: "text-[#0b86c4]", bg: "bg-tint-sky", dot: "bg-sky", hex: colors.sky },
  info: { label: "Info", text: "text-ink-2", bg: "bg-[#f1f4fa]", dot: "bg-ink-3", hex: colors.ink3 },
} as const;

export type Severity = keyof typeof severityStyles;

export const chartPalette = [colors.violet, colors.mint, colors.sky, colors.amber, colors.coral, colors.lavender];
