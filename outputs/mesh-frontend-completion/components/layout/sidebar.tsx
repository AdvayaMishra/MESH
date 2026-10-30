"use client";
import { isLive, logoutLive } from "@/lib/connected/live-state";
import { endDemoSession } from "@/lib/demo-session";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, ChevronsLeft, ChevronsUpDown, LogOut, PanelLeftOpen, UserRound } from "lucide-react";
import { Logo } from "@/components/layout/logo";
import { Avatar } from "@/components/ui/avatar";
import { Tip } from "@/components/ui/tooltip";
import { Dropdown, DropdownContent, DropdownItem, DropdownLabel, DropdownSeparator, DropdownTrigger } from "@/components/ui/dropdown";
import { sections, roleLabels, type NavSection } from "@/lib/nav";
import { ALL_ROLES, canAccess, roleHome } from "@/lib/permissions";
import { useUI } from "@/stores/ui-store";
import { accentStyles } from "@/lib/design-tokens";
import { cn } from "@/lib/utils/cn";
import { useDataset } from "@/lib/api";
import { tenantList } from "@/lib/api/mock";
import { useTenant } from "@/stores/tenant-store";
import { useWorkspace } from "@/stores/workspace-store";
import { toast } from "sonner";

function isActive(pathname: string, href: string, siblings: string[]) {
  if (pathname === href) return true;
  // a parent route is active only if no more specific sibling matches
  const moreSpecific = siblings.some((s) => s !== href && s.startsWith(href) && pathname.startsWith(s));
  return pathname.startsWith(href + "/") && !moreSpecific;
}

export function SidebarContent({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const { currentUser, org } = useDataset();
  const orgId = useTenant((s) => s.orgId);
  const pathname = usePathname();
  const router = useRouter();
  const { role, setRole, toggleSidebar } = useUI();
  // Per-item filtering driven by the central permission config; sections with no visible items disappear.
  const workspace = useWorkspace();
  const counts: Record<string, number> = {
    "/owner/projects": workspace.projects.filter((p) => p.status === "Awaiting approval").length,
    "/people/verification": workspace.idSubmissions.filter((p) => p.status === "Pending review").length,
    "/devtrack/security": workspace.findings.filter((p) => p.status === "Open").length,
    "/vader/incidents": workspace.incidents.filter((p) => p.status !== "Resolved").length,
  };
  const visible = sections
    .map((s) => ({ ...s, items: s.items.filter((i) => canAccess(role, i.href)).map((i) => ({ ...i, badge: i.href in counts ? (counts[i.href] ? String(counts[i.href]) : undefined) : i.badge })) }))
    .filter((s) => s.items.length > 0);
  const [open, setOpen] = React.useState<Record<string, boolean>>({});

  const isOpen = (s: NavSection) => open[s.id] ?? true;

  return (
    <div className="flex h-full flex-col">
      {/* Brand + org switcher */}
      <div className={cn("flex items-center gap-2 px-4 pt-5", collapsed && "justify-center px-2")}>
        <Link href={roleHome[role]} aria-label="MESH home" onClick={onNavigate}>
          <Logo collapsed={collapsed} />
        </Link>
      </div>
      <div className={cn("px-3 pt-4", collapsed && "px-2")}>
        <Dropdown>
          <DropdownTrigger asChild>
            <button
              className={cn(
                "flex w-full items-center gap-2.5 rounded-xl border border-line bg-white p-2 text-left transition-colors hover:border-violet/30 hover:bg-tint-violet",
                collapsed && "justify-center border-transparent bg-transparent p-1"
              )}
              aria-label="Switch organization"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg gradient-mint text-xs font-bold text-white">{org.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}</span>
              {!collapsed && (
                <>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-ink">{org.name}</span>
                    <span className="block truncate text-xs text-ink-3">{org.plan}{!isLive()&&" · simulated org"}</span>
                  </span>
                  <ChevronsUpDown className="size-4 text-ink-3" />
                </>
              )}
            </button>
          </DropdownTrigger>
          <DropdownContent align="start" className="w-64">
            <DropdownLabel>Organizations</DropdownLabel>
            {(isLive()?[{id:orgId,org,simulatedLabel:"Connected organization"}]:tenantList).map((o) => {
              const current = o.id === orgId;
              return (
                <DropdownItem
                  key={o.id}
                  onSelect={() => {
                    if (current) return;
                    useWorkspace.getState().switchOrg(o.id);
                    useTenant.getState().setOrg(o.id);
                    onNavigate?.();
                    toast.success(`Switched to ${o.org.name}`, { description: "Simulated organization — its data is separate from other demo organizations." });
                    router.push(roleHome[role]);
                  }}
                >
                  <span className="flex-1">
                    {o.org.name}
                    <span className="block text-xs text-ink-3">{o.simulatedLabel}</span>
                  </span>
                  {current && <Check className="size-4 !text-violet" />}
                </DropdownItem>
              );
            })}
          </DropdownContent>
        </Dropdown>
      </div>

      {/* Navigation */}
      <nav aria-label="Primary" className="no-scrollbar mt-4 flex-1 space-y-4 overflow-y-auto px-3 pb-4">
        {visible.map((section) => {
          const a = accentStyles[section.accent === "cyan" ? "cyan" : section.accent];
          const hrefs = section.items.map((i) => i.href);
          return (
            <div key={section.id}>
              {!collapsed ? (
                <button
                  onClick={() => setOpen((o) => ({ ...o, [section.id]: !isOpen(section) }))}
                  className="mb-1 flex w-full items-center justify-between rounded-lg px-2 py-1 text-xs font-semibold text-ink-3 hover:text-ink-2"
                  aria-expanded={isOpen(section)}
                >
                  <span className="flex items-center gap-2">
                    <span className="size-2 rounded-full" style={{ background: a.hex }} />
                    {section.label}
                  </span>
                  <ChevronDown className={cn("size-3.5 transition-transform", !isOpen(section) && "-rotate-90")} />
                </button>
              ) : (
                <div className="mx-auto mb-1 h-px w-6 bg-line" />
              )}
              <AnimatePresence initial={false}>
                {(isOpen(section) || collapsed) && (
                  <motion.ul
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-0.5 overflow-hidden"
                  >
                    {section.items.map((item) => {
                      const active = isActive(pathname, item.href, hrefs);
                      const link = (
                        <Link
                          href={item.href}
                          onClick={onNavigate}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "group relative flex items-center gap-3 rounded-xl px-2.5 py-2 text-[13.5px] font-medium transition-colors",
                            collapsed && "justify-center px-0",
                            active ? "bg-tint-violet text-indigo" : "text-ink-2 hover:bg-[#f1f4fb] hover:text-ink"
                          )}
                        >
                          {active && <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full" style={{ background: a.hex }} />}
                          <item.icon className="size-[18px] shrink-0" style={active ? { color: a.hex === "#67E8F9" ? "#0e9db5" : a.hex } : undefined} />
                          {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
                          {item.badge && !collapsed && (
                            <span className="rounded-full bg-coral px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">{item.badge}</span>
                          )}
                          {item.badge && collapsed && <span className="absolute right-2 top-1.5 size-2 rounded-full bg-coral ring-2 ring-white" />}
                        </Link>
                      );
                      return (
                        <li key={item.href}>
                          {collapsed ? (
                            <Tip label={item.label} side="right">
                              {link}
                            </Tip>
                          ) : (
                            link
                          )}
                        </li>
                      );
                    })}
                  </motion.ul>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </nav>

      {/* Footer: collapse + profile */}
      <div className="border-t border-line p-3">
        <button
          onClick={toggleSidebar}
          className={cn("mb-2 hidden w-full items-center gap-2 rounded-xl px-2.5 py-2 text-[13px] text-ink-3 hover:bg-[#f1f4fb] hover:text-ink lg:flex", collapsed && "justify-center px-0")}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen className="size-[18px]" /> : <ChevronsLeft className="size-[18px]" />}
          {!collapsed && "Collapse"}
        </button>
        <Dropdown>
          <DropdownTrigger asChild>
            <button className={cn("flex w-full items-center gap-2.5 rounded-xl p-2 text-left hover:bg-[#f1f4fb]", collapsed && "justify-center p-1")} aria-label="Account menu">
              <Avatar src={currentUser.photo} name={currentUser.name} size={34} />
              {!collapsed && (
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-ink">{currentUser.name}</span>
                  <span className="block truncate text-xs text-ink-3">{roleLabels[role]} view</span>
                </span>
              )}
            </button>
          </DropdownTrigger>
          <DropdownContent align="start" side="top" className="w-64">
            <DropdownLabel>{isLive()?"Signed-in account":"Preview MESH as…"}</DropdownLabel>
            {(isLive()?[]:ALL_ROLES).map((r) => (
              <DropdownItem
                key={r}
                onSelect={() => {
                  setRole(r);
                  // Leave the current page if the new role can't open it.
                  if (!canAccess(r, pathname)) router.push(roleHome[r]);
                  onNavigate?.();
                }}
              >
                <span className="flex-1">{roleLabels[r]}</span>
                {role === r && <Check className="size-4 !text-violet" />}
              </DropdownItem>
            ))}
            <DropdownSeparator />
            <DropdownItem icon={<UserRound />} onSelect={() => router.push("/workspace/settings")}>
              Profile settings
            </DropdownItem>
            <DropdownItem icon={<LogOut />} onSelect={()=>{if(isLive())void logoutLive().finally(()=>{router.push("/login");router.refresh();});else endDemoSession();}}>
              Sign out
            </DropdownItem>
          </DropdownContent>
        </Dropdown>
      </div>
    </div>
  );
}

export function Sidebar() {
  const collapsed = useUI((s) => s.sidebarCollapsed);
  return (
    <motion.aside
      animate={{ width: collapsed ? 76 : 268 }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      className="sticky top-0 hidden h-dvh shrink-0 border-r border-line bg-white/90 backdrop-blur lg:block"
    >
      <SidebarContent collapsed={collapsed} />
    </motion.aside>
  );
}
