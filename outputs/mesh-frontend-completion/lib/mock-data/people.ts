import type { Employee, TrustEvent } from "@/lib/types";
import { TRUST_START, clampScore, isTrustEligible } from "@/lib/trust";

export const ORG = {
  name: "Lumen Robotics",
  domain: "lumenrobotics.io",
  plan: "Enterprise",
  region: "Bengaluru, IN",
};

export const CURRENT_USER = { id: "LR-1001", name: "Alex Morgan", email: "alex@lumenrobotics.io", role: "Owner & CEO" };

/** `delta` is given in stars for readability (0.1 star = 1 point) and stored in points. */
const ev = (id: string, date: string, delta: number, reason: string, source: string, reviewedBy?: string): TrustEvent => ({
  id,
  date,
  delta: Math.round(delta * 10),
  reason,
  source,
  reviewedBy,
});

type Seed = Omit<Employee, "trustEvents" | "trustScore" | "email" | "location" | "salaryBand"> & { trustEvents?: TrustEvent[] };

/** Target scores (points) for eligible employees; the gap to 20 + listed events becomes one aggregated, reviewed history event. */
const TRUST_TARGET: Record<string, number> = {
  "LR-1010": 38, "LR-1011": 36, "LR-1012": 33, "LR-1020": 31, "LR-1021": 24, "LR-1022": 30, "LR-1023": 27,
  "LR-1024": 29, "LR-1030": 41, "LR-1031": 37, "LR-1071": 20, "LR-1072": 20,
};

function buildTrust(s: Seed): Pick<Employee, "trustScore" | "trustEvents"> {
  if (!isTrustEligible(s)) return { trustScore: null, trustEvents: [] };
  const listed = s.trustEvents ?? [];
  const target = TRUST_TARGET[s.id] ?? TRUST_START;
  const gap = target - TRUST_START - listed.reduce((a, e) => a + e.delta, 0);
  const events: TrustEvent[] = [...listed];
  if (gap !== 0) events.push({ id: `${s.id}-agg`, date: "2026-09-01", delta: gap, reason: "Aggregated reviewed contributions before September 2026", source: "DevTrack", reviewedBy: "Performance review" });
  events.push({ id: `${s.id}-start`, date: s.joinDate, delta: 0, reason: "Starting score for eligible role: 20 / 50 (2 stars)", source: "System" });
  return { trustScore: clampScore(TRUST_START + events.reduce((a, e) => a + e.delta, 0)), trustEvents: events };
}

const seeds: Seed[] = [
  { id: "LR-1001", name: "Alex Morgan", role: "Owner & CEO", appRole: "owner", department: "Finance", status: "Active", verification: "Verified", joinDate: "2019-03-04", projects: [],riskScore: 8 },
  { id: "LR-1002", name: "Priya Raghunathan", role: "Head of People", appRole: "hr", department: "People Ops", status: "Active", verification: "Verified", joinDate: "2020-01-13", manager: "LR-1001", projects: [],riskScore: 12 },
  { id: "LR-1010", name: "Daniel Okafor", role: "Senior Software Engineer", appRole: "senior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2020-06-22", manager: "LR-1001", projects: ["PRJ-01", "PRJ-02"],riskScore: 18,
    trustEvents: [
      ev("t1", "2026-10-14", +0.2, "Merged 6 reviewed PRs with zero reverted changes", "DevTrack", "Priya Raghunathan"),
      ev("t2", "2026-09-30", +0.1, "Resolved 3 high-severity findings ahead of SLA", "DevTrack"),
      ev("t3", "2026-09-02", -0.1, "Missed one sprint review (approved leave not logged)", "People", "Priya Raghunathan"),
    ] },
  { id: "LR-1011", name: "Meera Iyer", role: "Senior Backend Engineer", appRole: "senior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2021-02-08", manager: "LR-1001", projects: ["PRJ-01", "PRJ-03"],riskScore: 22 },
  { id: "LR-1012", name: "Tomás Herrera", role: "Staff Platform Engineer", appRole: "senior-dev", department: "Infrastructure", status: "Active", verification: "Verified", joinDate: "2019-09-16", manager: "LR-1001", projects: ["PRJ-04", "PRJ-05"],riskScore: 31 },
  { id: "LR-1020", name: "Aisha Khan", role: "Software Engineer II", appRole: "junior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2023-07-10", manager: "LR-1010", projects: ["PRJ-01", "PRJ-06"], riskScore: 14,
    trustEvents: [
      ev("t4", "2026-10-18", +0.2, "Proposal PRJ-07 approved with positive reviewer notes", "DevTrack", "Daniel Okafor"),
      ev("t5", "2026-10-02", +0.1, "Closed 9 tasks this sprint, 2 above plan", "DevTrack"),
      ev("t6", "2026-08-21", -0.1, "Gitleaks flagged a test token in a feature branch (rotated within 1h)", "DevTrack", "Daniel Okafor"),
    ] },
  { id: "LR-1021", name: "Rohan Desai", role: "Software Engineer I", appRole: "junior-dev", department: "Engineering", status: "Probation", verification: "Verified", joinDate: "2026-05-19", manager: "LR-1010", projects: ["PRJ-02"],riskScore: 27 },
  { id: "LR-1022", name: "Sofia Lindqvist", role: "Frontend Engineer", appRole: "junior-dev", department: "Engineering", status: "Active", verification: "Verified", joinDate: "2024-01-15", manager: "LR-1011", projects: ["PRJ-03", "PRJ-06"],riskScore: 16 },
  { id: "LR-1023", name: "Kwame Mensah", role: "QA Engineer", appRole: "junior-dev", department: "Engineering", status: "On leave", verification: "Verified", joinDate: "2022-11-28", manager: "LR-1011", projects: ["PRJ-03"],riskScore: 10 },
  { id: "LR-1024", name: "Ishaan Bhatt", role: "DevOps Engineer", appRole: "junior-dev", department: "Infrastructure", status: "Active", verification: "Verified", joinDate: "2023-03-06", manager: "LR-1012", projects: ["PRJ-04"],riskScore: 41,
    trustEvents: [
      ev("t7", "2026-10-21", 0, "Unusual after-hours database access flagged by VADER — under analyst review, no conclusion drawn", "VADER", "Nadia Farouk"),
      ev("t8", "2026-10-05", +0.2, "Reduced idle cloud spend by 11% on PRJ-04", "Owner"),
    ] },
  { id: "LR-1030", name: "Nadia Farouk", role: "Security Analyst", appRole: "security-analyst", department: "Security", status: "Active", verification: "Verified", joinDate: "2021-08-02", manager: "LR-1001", projects: ["PRJ-05"],riskScore: 6 },
  { id: "LR-1031", name: "Victor Almeida", role: "Security Engineer", appRole: "security-analyst", department: "Security", status: "Active", verification: "Verified", joinDate: "2022-04-18", manager: "LR-1030", projects: ["PRJ-05"],riskScore: 9 },
  { id: "LR-1040", name: "Hannah Weiss", role: "Head of Product", appRole: "hr", department: "Product", status: "Active", verification: "Verified", joinDate: "2020-10-05", manager: "LR-1001", projects: ["PRJ-06"],riskScore: 11 },
  { id: "LR-1041", name: "Lucas Moreau", role: "Product Designer", appRole: "junior-dev", department: "Design", status: "Active", verification: "Verified", joinDate: "2023-09-11", manager: "LR-1040", projects: ["PRJ-06"],riskScore: 13 },
  { id: "LR-1042", name: "Yuki Tanaka", role: "UX Researcher", appRole: "junior-dev", department: "Design", status: "Onboarding", verification: "Pending review", joinDate: "2026-10-19", manager: "LR-1040", projects: [],riskScore: 0 },
  { id: "LR-1050", name: "Carlos Vega", role: "Finance Manager", appRole: "hr", department: "Finance", status: "Active", verification: "Verified", joinDate: "2021-05-24", manager: "LR-1001", projects: [],riskScore: 15 },
  { id: "LR-1051", name: "Elena Petrova", role: "Financial Analyst", appRole: "junior-dev", department: "Finance", status: "Active", verification: "Verified", joinDate: "2024-06-03", manager: "LR-1050", projects: [],riskScore: 12 },
  { id: "LR-1060", name: "Jordan Blake", role: "Account Executive", appRole: "junior-dev", department: "Sales", status: "Active", verification: "Verified", joinDate: "2022-02-14", manager: "LR-1001", projects: [],riskScore: 19 },
  { id: "LR-1061", name: "Fatima Zahra", role: "Sales Development Rep", appRole: "junior-dev", department: "Sales", status: "Active", verification: "Verified", joinDate: "2025-03-17", manager: "LR-1060", projects: [],riskScore: 9 },
  { id: "LR-1062", name: "Marcus Chen", role: "Solutions Architect", appRole: "senior-dev", department: "Sales", status: "Offboarding", verification: "Verified", joinDate: "2020-12-07", manager: "LR-1060", projects: ["PRJ-02"],riskScore: 38 },
  { id: "LR-1070", name: "Anika Sharma", role: "Recruiter", appRole: "junior-dev", department: "People Ops", status: "Active", verification: "Verified", joinDate: "2024-09-02", manager: "LR-1002", projects: [],riskScore: 7 },
  { id: "LR-1071", name: "Samuel Osei", role: "Software Engineer I", appRole: "junior-dev", department: "Engineering", status: "Onboarding", verification: "Needs resubmission", joinDate: "2026-10-16", manager: "LR-1011", projects: [],riskScore: 0 },
  { id: "LR-1072", name: "Grace Liu", role: "Data Engineer", appRole: "junior-dev", department: "Engineering", status: "Onboarding", verification: "Pending review", joinDate: "2026-10-20", manager: "LR-1012", projects: [],riskScore: 0 },
];

export const employees: Employee[] = seeds.map((s) => ({
  ...s,
  email: `${s.name.toLowerCase().replace(/[^a-z ]/g, "").replace(/ /g, ".")}@${ORG.domain}`,
  location: ["Bengaluru", "Pune", "Remote — Berlin", "Remote — Lisbon", "Hyderabad", "Remote — Toronto"][parseInt(s.id.slice(-2), 10) % 6],
  salaryBand: s.department === "Engineering" || s.department === "Infrastructure" ? "Band E3" : s.department === "Security" ? "Band S2" : "Band G2",
  ...buildTrust(s),
}));

export const employeeById = (id: string) => employees.find((e) => e.id === id);
export const employeeName = (id: string) => employeeById(id)?.name ?? "Unassigned";

export const departmentStats = [
  { dept: "Engineering", headcount: 9, cloudSpend: 41200, budget: 46000 },
  { dept: "Infrastructure", headcount: 4, cloudSpend: 52800, budget: 55000 },
  { dept: "Security", headcount: 3, cloudSpend: 14300, budget: 18000 },
  { dept: "Product", headcount: 3, cloudSpend: 6900, budget: 9000 },
  { dept: "Design", headcount: 2, cloudSpend: 3100, budget: 5000 },
  { dept: "Sales", headcount: 3, cloudSpend: 5400, budget: 8000 },
];
