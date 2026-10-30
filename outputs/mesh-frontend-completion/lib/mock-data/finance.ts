export const monthlyCost = [
  { month: "Apr", actual: 98200, forecast: 98200 },
  { month: "May", actual: 101400, forecast: 101400 },
  { month: "Jun", actual: 104900, forecast: 104900 },
  { month: "Jul", actual: 109300, forecast: 109300 },
  { month: "Aug", actual: 113800, forecast: 113800 },
  { month: "Sep", actual: 118600, forecast: 118600 },
  { month: "Oct", actual: 123700, forecast: 123700 },
  { month: "Nov", actual: null as number | null, forecast: 129400 },
  { month: "Dec", actual: null as number | null, forecast: 134900 },
  { month: "Jan", actual: null as number | null, forecast: 139800 },
];

export const providerSplit = [
  { name: "AWS", value: 68200, color: "#635BFF" },
  { name: "Azure", value: 31900, color: "#38BDF8" },
  { name: "GCP", value: 23600, color: "#00C9A7" },
];

export const utilization = [
  { service: "Compute", used: 71, reserved: 88 },
  { service: "Storage", used: 64, reserved: 79 },
  { service: "Databases", used: 58, reserved: 82 },
  { service: "Network", used: 47, reserved: 60 },
  { service: "Kubernetes", used: 76, reserved: 90 },
];

export const orgKpis = {
  totalEmployees: 24,
  employeeDelta: 3,
  activeProjects: 5,
  projectDelta: 1,
  monthlyCloudSpend: 123700,
  spendDelta: 4.3,
  pendingApprovals: 3,
  openIncidents: 4,
  incidentDelta: -1,
  securityPosture: 82,
  postureDelta: 3,
};

export const kpiSparks = {
  employees: [18, 19, 19, 20, 21, 21, 24],
  projects: [3, 4, 4, 4, 5, 5, 5],
  spend: [98, 101, 105, 109, 114, 119, 124],
  approvals: [1, 2, 2, 4, 3, 2, 3],
  incidents: [7, 6, 6, 5, 5, 5, 4],
  posture: [71, 73, 74, 77, 78, 79, 82],
};

export const whatIfPrompts = [
  "What if we increase cloud capacity by 20%?",
  "Which department has the highest infrastructure cost?",
  "What happens if we reduce unused cloud resources?",
  "Which projects need additional resources?",
];

export const whatIfScenarios: Record<
  string,
  {
    headline: string;
    summary: string;
    assumptions: string[];
    series: { label: string; baseline: number; scenario: number }[];
    impact: { label: string; value: string; tone: "mint" | "amber" | "coral" | "violet" }[];
  }
> = {
  "What if we increase cloud capacity by 20%?": {
    headline: "Monthly spend rises about $18.6k, but peak-load headroom improves",
    summary:
      "A 20% capacity increase lifts monthly spend from $123.7k to roughly $142.3k. Compute and Kubernetes drive 74% of the change. Peak utilisation drops from 76% to 63%, which lowers the chance of throttling during release weeks.",
    assumptions: ["Pricing stays at current on-demand + reserved mix", "Traffic grows 6% per month", "No reserved-instance purchases", "Costs are projected from the last 6 months"],
    series: [
      { label: "Nov", baseline: 129400, scenario: 148900 },
      { label: "Dec", baseline: 134900, scenario: 155100 },
      { label: "Jan", baseline: 139800, scenario: 160600 },
      { label: "Feb", baseline: 144200, scenario: 165700 },
    ],
    impact: [
      { label: "Extra monthly cost", value: "+$18.6k", tone: "amber" },
      { label: "Peak utilisation", value: "76% → 63%", tone: "mint" },
      { label: "Throttling risk", value: "Medium → Low", tone: "mint" },
      { label: "Budget overrun risk", value: "Dec", tone: "coral" },
    ],
  },
  "Which department has the highest infrastructure cost?": {
    headline: "Infrastructure leads at $52.8k, 43% of total cloud spend",
    summary:
      "Infrastructure runs closest to its budget (96% used). Engineering follows at $41.2k. Two Kubernetes clusters owned by Infrastructure account for $9.4k of idle cost during nights and weekends.",
    assumptions: ["Costs allocated by resource tags", "Untagged resources (3%) assigned to Infrastructure", "October month-to-date, extrapolated"],
    series: [
      { label: "Infra", baseline: 52800, scenario: 55000 },
      { label: "Eng", baseline: 41200, scenario: 46000 },
      { label: "Security", baseline: 14300, scenario: 18000 },
      { label: "Product", baseline: 6900, scenario: 9000 },
    ],
    impact: [
      { label: "Top department", value: "Infrastructure", tone: "violet" },
      { label: "Share of spend", value: "43%", tone: "violet" },
      { label: "Budget used", value: "96%", tone: "amber" },
      { label: "Idle cost", value: "$9.4k", tone: "coral" },
    ],
  },
  "What happens if we reduce unused cloud resources?": {
    headline: "Rightsizing could save about $14.2k per month",
    summary:
      "Of 214 monitored resources, 37 are idle or oversized. Removing or resizing them saves roughly $14.2k per month (11.5%) with low risk. Three databases need an owner's confirmation before changes.",
    assumptions: ["Idle = under 5% CPU for 14 days", "Snapshots kept for 30 days", "Production databases excluded until owner approval"],
    series: [
      { label: "Nov", baseline: 129400, scenario: 115200 },
      { label: "Dec", baseline: 134900, scenario: 120700 },
      { label: "Jan", baseline: 139800, scenario: 125600 },
      { label: "Feb", baseline: 144200, scenario: 130000 },
    ],
    impact: [
      { label: "Monthly savings", value: "$14.2k", tone: "mint" },
      { label: "Resources affected", value: "37", tone: "violet" },
      { label: "Risk to uptime", value: "Low", tone: "mint" },
      { label: "Needs approval", value: "3 DBs", tone: "amber" },
    ],
  },
  "Which projects need additional resources?": {
    headline: "Orbit and Forge show the largest resourcing gaps",
    summary:
      "Orbit Customer Portal has spent 81% of budget at 48% progress and is behind its November deadline. Forge CI/CD is at 39% progress with the highest priority; adding one platform engineer for 6 weeks closes the gap.",
    assumptions: ["Burn rate measured over the last 4 sprints", "Velocity from DevTrack", "Capacity includes approved leave"],
    series: [
      { label: "Orbit", baseline: 48, scenario: 74 },
      { label: "Forge", baseline: 39, scenario: 63 },
      { label: "Atlas", baseline: 72, scenario: 78 },
      { label: "Pulse", baseline: 86, scenario: 88 },
    ],
    impact: [
      { label: "Projects at risk", value: "2", tone: "coral" },
      { label: "Suggested capacity", value: "+1.5 FTE", tone: "violet" },
      { label: "Orbit budget used", value: "81%", tone: "amber" },
      { label: "Forge priority", value: "Critical", tone: "coral" },
    ],
  },
};
