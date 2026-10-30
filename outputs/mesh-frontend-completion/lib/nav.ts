import {
  LayoutDashboard, Wallet, FolderKanban, Sparkles, Users, UserCheck, CalendarDays, Banknote, UserCog,
  Code2, ShieldCheck, GitPullRequest, ListChecks, Radar, Gauge, Network, Activity, Cloud, Siren, Bot,
  FlaskConical, MessageSquareWarning, TrendingUp, CalendarPlus, Bell, ScrollText, FileBarChart, Settings, LifeBuoy, Building2, Rss, type LucideIcon,
} from "lucide-react";
import type { Role } from "@/lib/types";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
}
export interface NavSection {
  id: "owner" | "people" | "devtrack" | "vader" | "workspace";
  label: string;
  accent: "violet" | "mint" | "sky" | "cyan" | "amber";
  items: NavItem[];
}

export const sections: NavSection[] = [
  {
    id: "owner", label: "MESH Owner", accent: "violet",
    items: [
      { label: "Overview", href: "/owner", icon: LayoutDashboard },
      { label: "Finance", href: "/owner/finance", icon: Wallet },
      { label: "Projects & approvals", href: "/owner/projects", icon: FolderKanban, badge: "3" },
      { label: "Team performance", href: "/owner/performance", icon: Sparkles },
    ],
  },
  {
    id: "people", label: "MESH People", accent: "mint",
    items: [
      { label: "Overview", href: "/people", icon: LayoutDashboard },
      { label: "Directory", href: "/people/directory", icon: Users },
      { label: "Administration", href: "/people/administration", icon: UserCog },
      { label: "Verification", href: "/people/verification", icon: UserCheck, badge: "2" },
      { label: "Payroll & leave", href: "/people/payroll", icon: Banknote },
      { label: "Leave approvals", href: "/people/leave/review", icon: CalendarDays },
      { label: "Complaints", href: "/people/complaints", icon: MessageSquareWarning },
      { label: "Promotions", href: "/people/promotions", icon: TrendingUp },
      { label: "Lifecycle", href: "/people/lifecycle", icon: UserCog },
      { label: "Leave calendar", href: "/people/leave", icon: CalendarDays },
    ],
  },
  {
    id: "devtrack", label: "DevTrack", accent: "sky",
    items: [
      { label: "Dashboard", href: "/devtrack", icon: Code2 },
      { label: "Projects", href: "/devtrack/projects", icon: FolderKanban },
      { label: "Board", href: "/devtrack/board", icon: ListChecks },
      { label: "Sprints", href: "/devtrack/sprints", icon: CalendarDays },
      { label: "Pull requests", href: "/devtrack/pull-requests", icon: GitPullRequest },
      { label: "Code security", href: "/devtrack/security", icon: ShieldCheck, badge: "5" },
    ],
  },
  {
    id: "vader", label: "VADER", accent: "cyan",
    items: [
      { label: "Command center", href: "/vader", icon: Radar },
      { label: "Risk analytics", href: "/vader/risk", icon: Gauge },
      { label: "Attack chains", href: "/vader/attack-chain", icon: Network },
      { label: "Behavior", href: "/vader/behavior", icon: Activity },
      { label: "Cloud security", href: "/vader/cloud", icon: Cloud },
      { label: "Incidents", href: "/vader/incidents", icon: Siren, badge: "4" },
      { label: "AI Copilot", href: "/vader/copilot", icon: Bot },
      { label: "Simulation lab", href: "/vader/simulation", icon: FlaskConical },
    ],
  },
  {
    id: "workspace", label: "Workspace", accent: "amber",
    items: [
      { label: "My complaints", href: "/workspace/complaints", icon: MessageSquareWarning },
      { label: "Trust Stars", href: "/workspace/trust", icon: ShieldCheck },
      { label: "AI insights", href: "/workspace/insights", icon: Sparkles },
      { label: "My leave", href: "/workspace/leave", icon: CalendarPlus },
      { label: "Notifications", href: "/workspace/notifications", icon: Bell },
      { label: "Activity", href: "/workspace/activity", icon: Rss },
      { label: "Reports", href: "/workspace/reports", icon: FileBarChart },
      { label: "Audit log", href: "/workspace/audit", icon: ScrollText },
      { label: "Organization", href: "/workspace/organization", icon: Building2 },
      { label: "Settings", href: "/workspace/settings", icon: Settings },
      { label: "Help", href: "/workspace/help", icon: LifeBuoy },
    ],
  },
];

export const roleLabels: Record<Role, string> = {
  owner: "Owner",
  hr: "HR",
  "senior-dev": "Senior Developer",
  "junior-dev": "Junior Developer",
  "security-analyst": "Security Analyst",
};
