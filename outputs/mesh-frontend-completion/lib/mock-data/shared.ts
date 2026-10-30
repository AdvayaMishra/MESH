import type { AuditEntry, Notification } from "@/lib/types";

export const notifications: Notification[] = [
  { id: "N-1", title: "Critical incident INC-3021", body: "Correlated chain ending in a 1.8 GB external download.", at: "2026-10-23T02:20:00Z", module: "VADER", read: false, href: "/vader/incidents/INC-3021", tone: "coral" },
  { id: "N-2", title: "3 projects awaiting your approval", body: "Vista, Relay and Keep need a decision.", at: "2026-10-23T08:05:00Z", module: "Owner", read: false, href: "/owner/projects", tone: "violet" },
  { id: "N-3", title: "ID submitted by Yuki Tanaka", body: "OCR is ready for human review.", at: "2026-10-22T16:41:00Z", module: "People", read: false, href: "/people/verification", tone: "mint" },
  { id: "N-4", title: "Gitleaks finding in forge-pipelines", body: "A credential pattern was detected and redacted.", at: "2026-10-22T23:36:00Z", module: "DevTrack", read: true, href: "/devtrack/security", tone: "amber" },
  { id: "N-5", title: "Budget alert: Infrastructure at 96%", body: "Projected to exceed budget on Dec 4.", at: "2026-10-22T07:00:00Z", module: "Owner", read: true, href: "/owner", tone: "amber" },
  { id: "N-6", title: "Scan authorization revoked for lumen-ui", body: "Re-authorize the repository to resume scans.", at: "2026-10-21T12:00:00Z", module: "DevTrack", read: true, href: "/devtrack/security", tone: "sky" },
];

export const activityFeed = [
  { id: "A-1", at: "2026-10-23T09:48:00Z", actor: "Daniel Okafor", text: "approved Aisha Khan's pull request in atlas-console-web", module: "DevTrack" as const },
  { id: "A-2", at: "2026-10-23T09:12:00Z", actor: "Nadia Farouk", text: "opened investigation on INC-3021", module: "VADER" as const },
  { id: "A-3", at: "2026-10-23T08:40:00Z", actor: "Priya Raghunathan", text: "scheduled offboarding for Marcus Chen", module: "People" as const },
  { id: "A-4", at: "2026-10-23T08:05:00Z", actor: "Keep Secrets Vault Migration", text: "was submitted for approval by Daniel Okafor", module: "Owner" as const },
  { id: "A-5", at: "2026-10-22T17:30:00Z", actor: "Victor Almeida", text: "marked INC-3023 as contained", module: "VADER" as const },
  { id: "A-6", at: "2026-10-22T15:02:00Z", actor: "Grace Liu", text: "submitted an employee ID for verification", module: "People" as const },
];

export const auditLog: AuditEntry[] = [
  { id: "AU-9001", at: "2026-10-23T09:50:00Z", actor: "Alex Morgan", action: "Viewed financial overview", target: "Owner · Cloud spend", module: "Owner", result: "Success", ip: "103.21.58.14" },
  { id: "AU-9000", at: "2026-10-23T09:12:00Z", actor: "Nadia Farouk", action: "Opened incident", target: "INC-3021", module: "VADER", result: "Success", ip: "10.20.4.18" },
  { id: "AU-8999", at: "2026-10-23T08:41:00Z", actor: "Priya Raghunathan", action: "Scheduled offboarding", target: "LR-1062 Marcus Chen", module: "People", result: "Simulated", ip: "10.20.4.9" },
  { id: "AU-8998", at: "2026-10-23T08:02:00Z", actor: "Daniel Okafor", action: "Submitted project proposal", target: "PRJ-09 Keep", module: "DevTrack", result: "Success", ip: "10.20.5.31" },
  { id: "AU-8997", at: "2026-10-22T19:22:00Z", actor: "Ishaan Bhatt", action: "Requested access to prod-orders-db", target: "prod-orders-db", module: "VADER", result: "Denied", ip: "10.20.7.44" },
  { id: "AU-8996", at: "2026-10-22T16:41:00Z", actor: "Yuki Tanaka", action: "Uploaded employee ID", target: "LR-1042", module: "People", result: "Success", ip: "49.37.12.201" },
  { id: "AU-8995", at: "2026-10-22T12:30:00Z", actor: "System", action: "Scheduled repository scan", target: "forge-pipelines", module: "DevTrack", result: "Simulated", ip: "—" },
  { id: "AU-8994", at: "2026-10-21T11:58:00Z", actor: "Alex Morgan", action: "Revoked scan authorization", target: "lumen-ui", module: "DevTrack", result: "Success", ip: "103.21.58.14" },
  { id: "AU-8993", at: "2026-10-20T10:12:00Z", actor: "Carlos Vega", action: "Exported payroll summary", target: "Payroll · September", module: "People", result: "Simulated", ip: "10.20.4.22" },
];

export const leaveRequests = [
  { id: "L-1", employee: "LR-1023", type: "Medical leave", from: "2026-10-12", to: "2026-11-06", days: 20, status: "Approved" },
  { id: "L-2", employee: "LR-1022", type: "Annual leave", from: "2026-11-24", to: "2026-11-28", days: 5, status: "Pending" },
  { id: "L-3", employee: "LR-1011", type: "Annual leave", from: "2026-12-22", to: "2027-01-02", days: 8, status: "Pending" },
  { id: "L-4", employee: "LR-1060", type: "Casual leave", from: "2026-10-30", to: "2026-10-30", days: 1, status: "Pending" },
  { id: "L-5", employee: "LR-1041", type: "Annual leave", from: "2026-11-10", to: "2026-11-12", days: 3, status: "Approved" },
];

export const payrollSummary = {
  month: "October 2026",
  gross: 412600,
  net: 331900,
  taxes: 58300,
  benefits: 22400,
  headcount: 24,
  trend: [
    { month: "May", gross: 371000 }, { month: "Jun", gross: 380500 }, { month: "Jul", gross: 389200 },
    { month: "Aug", gross: 396800 }, { month: "Sep", gross: 404100 }, { month: "Oct", gross: 412600 },
  ],
  byDept: [
    { dept: "Engineering", amount: 168400 }, { dept: "Infrastructure", amount: 79200 }, { dept: "Security", amount: 52100 },
    { dept: "Product", amount: 41300 }, { dept: "Sales", amount: 36800 }, { dept: "Finance", amount: 21600 }, { dept: "People Ops", amount: 13200 },
  ],
  discrepancies: [
    { id: "D-1", employee: "LR-1021", issue: "Pro-rated salary differs from contract by $412", suggestion: "Probation period end date may be misrecorded" },
    { id: "D-2", employee: "LR-1062", issue: "Final settlement includes 6 days of unused leave not in records", suggestion: "Confirm leave balance before processing" },
    { id: "D-3", employee: "LR-1072", issue: "Joining bonus missing from onboarding checklist", suggestion: "Add bonus line item if it is in the offer letter" },
  ],
};

export const idSubmissions = [
  { id: "V-501", employee: "LR-1042", submittedAt: "2026-10-22T16:41:00Z", docType: "Government photo ID", status: "Pending review" as const,
    submitted: { name: "Yuki Tanaka", dob: "1996-04-12", idNumber: "••••••7841", expiry: "2031-08-30" },
    ocr: { name: "YUKI TANAKA", dob: "1996-04-12", idNumber: "••••••7841", expiry: "2031-08-30" }, confidence: { name: 0.98, dob: 0.97, idNumber: 0.93, expiry: 0.95 }, history: [] as { at: string; by: string; action: string; note: string }[] },
  { id: "V-502", employee: "LR-1072", submittedAt: "2026-10-23T09:02:00Z", docType: "Government photo ID", status: "Pending review" as const,
    submitted: { name: "Grace Liu", dob: "1998-11-03", idNumber: "••••••2210", expiry: "2029-02-11" },
    ocr: { name: "GRACE LIU", dob: "1998-11-08", idNumber: "••••••2210", expiry: "2029-02-11" }, confidence: { name: 0.96, dob: 0.71, idNumber: 0.9, expiry: 0.94 }, history: [] },
  { id: "V-503", employee: "LR-1071", submittedAt: "2026-10-17T11:20:00Z", docType: "Government photo ID", status: "Needs resubmission" as const,
    submitted: { name: "Samuel Osei", dob: "1999-02-20", idNumber: "••••••9034", expiry: "2028-06-01" },
    ocr: { name: "SAMUEL O", dob: "1999-02-20", idNumber: "••••••90", expiry: "—" }, confidence: { name: 0.62, dob: 0.88, idNumber: 0.41, expiry: 0.2 },
    history: [{ at: "2026-10-18T09:00:00Z", by: "Priya Raghunathan", action: "Requested resubmission", note: "Image was cropped; the expiry date and last digits were not readable." }] },
];
