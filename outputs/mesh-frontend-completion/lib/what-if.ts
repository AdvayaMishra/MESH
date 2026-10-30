/** Deterministic demo model: a percentage change applied uniformly to forecast spend. */
export function modelSpendQuestion(question: string, monthlyCost: { month: string; actual: number | null; forecast: number }[]) {
  const q = question.toLowerCase();
  if (!/\b(cloud|spend|cost|budget|bill)\b/.test(q)) return null;
  if (/[+-]\s*\d/.test(q) || [...q.matchAll(/\d+(?:\.\d+)?\s*(?:%|percent\b)/g)].length !== 1) return null;
  const match = q.match(/\b(\d+(?:\.\d+)?)\s*(?:%|percent\b)/);
  const up = /\b(increase|increases|increased|raise|raises|grow|grows|higher|up)\b/.test(q);
  const down = /\b(decrease|decreases|reduce|reduces|cut|cuts|lower|save|saves|down)\b/.test(q);
  if (!match || up === down) return null;
  const percent = Number(match[1]);
  if (!Number.isFinite(percent) || percent <= 0 || percent > 100) return null;
  const factor = (up ? 1 : -1) * percent / 100;
  const forecasts = monthlyCost.filter((m) => m.actual === null);
  const basis = forecasts.length ? forecasts : monthlyCost.slice(-3);
  if (!basis.length) return null;
  const series = basis.map((m) => ({ label: m.month, baseline: m.forecast, scenario: Math.round(m.forecast * (1 + factor)) }));
  const first = series[0];
  const money = (n: number) => `$${n.toLocaleString("en-US")}`;
  return {
    headline: `A ${percent}% ${up ? "increase" : "decrease"} changes ${first.label} forecast spend to ${money(first.scenario)}`,
    summary: `The ${first.label} baseline is ${money(first.baseline)}; the illustrative difference is ${money(Math.abs(first.scenario - first.baseline))}. This is arithmetic on seeded forecasts, not an AI prediction.`,
    assumptions: ["The same percentage applies to total forecast spend in each displayed month.", "Prices, usage mix, and all other factors remain unchanged.", "This model does not estimate service capacity, operational risk, or actual savings."],
    series,
    impact: [
      { label: "Change", value: `${up ? "+" : "−"}${percent}%`, tone: "violet" as const },
      { label: `${first.label} difference`, value: `${up ? "+" : "−"}${money(Math.abs(first.scenario - first.baseline))}`, tone: up ? "amber" as const : "mint" as const },
    ],
  };
}
