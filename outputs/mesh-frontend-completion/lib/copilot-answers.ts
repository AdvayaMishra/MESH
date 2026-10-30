/**
 * Simulated VADER Copilot answers, built ONLY from the active tenant's dataset (no hardcoded organization facts).
 * This is a rule-based summariser over seeded data — not a language model. The UI labels it "Simulated AI".
 */
import type { Dataset } from "@/lib/api/dataset";

export interface Answer { text: string; bullets?: string[]; refs: { label: string; href: string }[]; details: string[]; next?: string }

export const COPILOT_PROMPTS = [
  "Why did our risk score increase?",
  "Summarize today's critical incidents.",
  "Which resources have excessive permissions?",
  "Explain this attack chain.",
  "What should the security analyst investigate next?",
];

const SEV = { critical: 0, high: 1, medium: 2, low: 3 } as const;
const sevRank = (s: string) => SEV[s as keyof typeof SEV] ?? 4;
const incRef = (id: string) => ({ label: id, href: `/vader/incidents/${id}` });
const hhmm = (iso: string) => iso.slice(11, 16);

type Src = Pick<Dataset, "incidents" | "riskComponents" | "riskTrend" | "cloudResources" | "attackChain">;

export function buildCopilotAnswers(d: Src): Record<string, Answer> {
  const open = d.incidents.filter((i) => i.status === "Open" || i.status === "Investigating").sort((a, b) => sevRank(a.severity) - sevRank(b.severity));
  const chainInc = d.incidents.find((i) => i.chainId);
  const rising = d.riskComponents.filter((c) => c.trend > 0).sort((a, b) => b.trend - a.trend).slice(0, 3);
  const falling = d.riskComponents.filter((c) => c.trend < 0).sort((a, b) => a.trend - b.trend);
  const from = d.riskTrend[Math.max(0, d.riskTrend.length - 4)]?.score ?? 0;
  const to = d.riskTrend[d.riskTrend.length - 1]?.score ?? 0;
  const sensitive = d.cloudResources.filter((r) => r.risk === "critical" || r.risk === "high");
  const chain = d.attackChain;
  const spanMin = chain.length > 1 ? Math.round((Date.parse(chain[chain.length - 1].at) - Date.parse(chain[0].at)) / 60000) : 0;
  const crit = open.filter((i) => i.severity === "critical").length;
  const high = open.filter((i) => i.severity === "high").length;

  const pairs: string[] = [];
  for (let i = 0; i < chain.length; i += 2) {
    const a = chain[i], b = chain[i + 1];
    pairs.push(b ? `${hhmm(a.at)} ${a.label.toLowerCase()} → ${hhmm(b.at)} ${b.label.toLowerCase()}` : `${hhmm(a.at)} ${a.label.toLowerCase()}`);
  }

  const priorities = [
    ...open.slice(0, 2).map((i) => `Investigate ${i.id}: ${i.title}`),
    ...sensitive.slice(0, 2).map((r) => `Review ${r.name} (${r.type}): ${r.issue}`),
  ];

  return {
    [COPILOT_PROMPTS[0]]: {
      text: `Risk moved from ${from} to ${to} over the last three days.${rising.length ? ` ${rising.length} area${rising.length > 1 ? "s" : ""} worsened together.` : ""}`,
      bullets: [...rising.map((c) => `${c.name} +${c.trend} (score ${c.score}, weight ${c.weight}%)`), ...falling.map((c) => `${c.name} ${c.trend} partly offset the rise`)],
      refs: [...open.slice(0, 2).map((i) => incRef(i.id)), { label: "Risk analytics", href: "/vader/risk" }],
      details: [`Weights: ${rising.map((c) => `${c.name.toLowerCase()} ${c.weight}%`).join(", ") || "n/a"}`, `Score uses ${d.riskComponents.length} components`, "Seeded risk components do not establish causal attribution to an incident"],
      next: open[0] ? `Start with ${open[0].id}: ${open[0].title}.` : undefined,
    },
    [COPILOT_PROMPTS[1]]: {
      text: open.length ? `There ${crit + high === 1 ? "is" : "are"} ${crit} critical and ${high} high-severity incident${crit + high === 1 ? "" : "s"} open right now (${open.length} open in total).` : "There are no open incidents right now.",
      bullets: open.slice(0, 4).map((i) => `${i.id} (${i.severity}): ${i.title}`),
      refs: open.slice(0, 3).map((i) => incRef(i.id)),
      details: ["Source: this organization's demo incident state", "These are signals for an analyst to verify, not confirmed breaches"],
      next: open[0] ? `Start with ${open[0].id}.` : undefined,
    },
    [COPILOT_PROMPTS[2]]: {
      text: sensitive.length ? `${sensitive.length} resource${sensitive.length > 1 ? "s" : ""} stand out for risky permissions or exposure.` : "No critical or high-risk resources were found in the cloud inventory.",
      bullets: sensitive.map((r) => `${r.name} (${r.provider} ${r.type}): ${r.issue}`),
      refs: [{ label: "Cloud inventory", href: "/vader/cloud" }],
      details: ["Method: cloud inventory findings rated high or critical", "Suggested policy: least privilege with named resources"],
      next: sensitive[0] ? `Draft a scoped fix for ${sensitive[0].name} and send it for owner approval.` : undefined,
    },
    [COPILOT_PROMPTS[3]]: chain.length
      ? {
          text: `${chain.length} correlated events form a plausible path${spanMin ? `, spanning ${spanMin} minutes` : ""}${chainInc ? ` (${chainInc.id})` : ""}.`,
          bullets: pairs,
          refs: [{ label: "Attack chain", href: "/vader/attack-chain" }, ...(chainInc ? [incRef(chainInc.id)] : [])],
          details: [`Sources joined: ${[...new Set(chain.map((n) => n.source))].join(", ")}`, "Alternative explanation to rule out: an approved change or scheduled job"],
          next: "Confirm with the account owner whether any planned activity explains these events.",
        }
      : { text: "No attack chain is recorded for this organization.", refs: [], details: [] },
    [COPILOT_PROMPTS[4]]: {
      text: priorities.length ? "Prioritise in this order. This list is sorted by severity; risk reduction has not been measured." : "Nothing urgent is open right now.",
      bullets: priorities,
      refs: [{ label: "Incidents", href: "/vader/incidents" }, { label: "Cloud security", href: "/vader/cloud" }],
      details: ["Ranking: incident severity, then cloud exposure", "Actions are suggestions; each needs analyst approval"],
    },
  };
}

/**
 * Free-text demo assistant. It never calls a model or fabricates facts: it searches
 * the currently selected organization's in-memory incident and asset records.
 */
export function answerCopilotQuestion(question: string, d: Src): Answer {
  const q = question.toLowerCase().trim();
  const canned = buildCopilotAnswers(d);
  if (canned[question]) return canned[question];
  const namedIncident = /\binc-[a-z0-9-]+\b/i.test(q);
  const namedResource = d.cloudResources.some((resource) => q.includes(resource.name.toLowerCase()));
  if (!namedIncident && !namedResource && /\b(permissions?|iam|privileges?|cloud|exposure|assets?)\b/.test(q)) return canned[COPILOT_PROMPTS[2]];
  const tokens = q.match(/[a-z0-9_-]{3,}/g)?.filter((t) => !["the", "and", "for", "are", "our", "how", "why", "can", "was", "has", "not", "but", "your", "their", "what", "which", "about", "show", "tell", "please", "with", "from", "this", "that", "there", "have", "does", "could", "would", "should", "explain", "summarize", "status", "incident", "incidents", "resource", "resources"].includes(t)) ?? [];
  const matchingIncidents = d.incidents.filter((i) => {
    const haystack = [i.id, i.title, i.summary, i.severity, i.status, ...(i.assets ?? [])].join(" ").toLowerCase();
    return tokens.some((t) => haystack.includes(t));
  }).slice(0, 5);
  const matchingAssets = d.cloudResources.filter((r) => {
    const haystack = [r.name, r.provider, r.type, r.issue, r.risk].join(" ").toLowerCase();
    return tokens.some((t) => haystack.includes(t));
  }).slice(0, 5);
  if (matchingIncidents.length || matchingAssets.length) {
    return {
      text: `I found ${matchingIncidents.length} matching incident${matchingIncidents.length === 1 ? "" : "s"} and ${matchingAssets.length} matching cloud resource${matchingAssets.length === 1 ? "" : "s"} in the active organization's demo data. These are possible keyword matches, not verified causal relationships.`,
      bullets: [
        ...matchingIncidents.map((i) => `${i.id} · ${i.title} (${i.severity}, ${i.status})`),
        ...matchingAssets.map((r) => `${r.name} · ${r.issue} (${r.risk})`),
      ],
      refs: [...matchingIncidents.map((i) => incRef(i.id)), ...(matchingAssets.length ? [{ label: "Cloud inventory", href: "/vader/cloud" }] : [])],
      details: ["Method: local keyword matching on this tenant's demo records", "No live log collection, external AI call or automated remediation"],
      next: "Open the linked records and verify the evidence before acting.",
    };
  }
  if (/risk|score|trend|increas|decreas/.test(q)) return canned[COPILOT_PROMPTS[0]];
  if (/permission|iam|privilege|cloud|expos|asset/.test(q)) return canned[COPILOT_PROMPTS[2]];
  if (/attack|chain|correlat|timeline/.test(q)) return canned[COPILOT_PROMPTS[3]];
  if (/priorit|investigat|next|urgent|recommend/.test(q)) return canned[COPILOT_PROMPTS[4]];
  if (/alert|critical|high|open|security/.test(q)) return canned[COPILOT_PROMPTS[1]];
  return {
    text: "I couldn't find a supported answer in this organization's demo records. Try asking about risk, incidents, cloud permissions, attack chains or a specific incident ID. This prototype does not use a live language model.",
    refs: [{ label: "Incidents", href: "/vader/incidents" }, { label: "Risk analytics", href: "/vader/risk" }],
    details: ["Scope: active tenant's seeded incident, risk and cloud data", "No evidence was found matching this question"],
  };
}
