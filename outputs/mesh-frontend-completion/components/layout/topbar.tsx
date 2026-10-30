"use client";
import { isLive, logoutLive } from "@/lib/connected/live-state";
import { endDemoSession } from "@/lib/demo-session";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, FolderPlus, Menu, Plus, ScanSearch, Search, UserPlus, ListPlus } from "lucide-react";
import { Dialog as D } from "radix-ui";
import { Button } from "@/components/ui/button";
import { Dropdown, DropdownContent, DropdownItem, DropdownLabel, DropdownTrigger } from "@/components/ui/dropdown";
import { NotificationsPopover } from "@/components/layout/notifications-popover";
import { SidebarContent } from "@/components/layout/sidebar";
import { LogoMark } from "@/components/layout/logo";
import { Avatar } from "@/components/ui/avatar";
import { canAccess } from "@/lib/permissions";
import { sections } from "@/lib/nav";
import { useUI } from "@/stores/ui-store";
import { useDataset } from "@/lib/api";

const moduleNames: Record<string, string> = {
  owner: "MESH Owner",
  people: "MESH People",
  devtrack: "DevTrack",
  vader: "VADER",
  workspace: "Workspace",
};

function useCrumbs() {
  const pathname = usePathname();
  const parts = pathname.split("/").filter(Boolean);
  const crumbs: { label: string; href?: string }[] = [];
  if (parts[0]) crumbs.push({ label: moduleNames[parts[0]] ?? parts[0], href: `/${parts[0]}` });
  const allItems = sections.flatMap((s) => s.items);
  const match = allItems.filter((i) => pathname === i.href || pathname.startsWith(i.href + "/")).sort((a, b) => b.href.length - a.href.length)[0];
  if (match && match.href !== `/${parts[0]}`) crumbs.push({ label: match.label, href: match.href });
  if (match && pathname !== match.href) {
    const rest = pathname.slice(match.href.length).split("/").filter(Boolean);
    rest.forEach((r) => crumbs.push({ label: decodeURIComponent(r).toUpperCase().match(/^[A-Z]{2,5}-\d+/) ? decodeURIComponent(r) : decodeURIComponent(r).replace(/-/g, " ") }));
  }
  if (crumbs.length === 1) crumbs[0] = { label: crumbs[0].label };
  return crumbs;
}

export function Topbar() {
  const { currentUser, org } = useDataset();
  const router = useRouter();
  const crumbs = useCrumbs();
  const { setCommand, mobileNavOpen, setMobileNav, role } = useUI();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur-md sm:px-6">
      <button
        className="flex size-10 items-center justify-center rounded-xl border border-line bg-white text-ink-2 lg:hidden"
        aria-label="Open navigation"
        onClick={() => setMobileNav(true)}
      >
        <Menu className="size-[18px]" />
      </button>

      <D.Root open={mobileNavOpen} onOpenChange={setMobileNav}>
        <D.Portal>
          <D.Overlay className="fixed inset-0 z-50 bg-[#172033]/35 backdrop-blur-[2px] lg:hidden" />
          <D.Content aria-describedby={undefined} className="fixed left-0 top-0 z-50 h-dvh w-[300px] max-w-[85vw] bg-white shadow-pop focus:outline-none lg:hidden">
            <D.Title className="sr-only">Navigation</D.Title>
            <SidebarContent collapsed={false} onNavigate={() => setMobileNav(false)} />
          </D.Content>
        </D.Portal>
      </D.Root>

      <span data-testid="active-org" className="inline-flex max-w-[11rem] shrink-0 items-center gap-1.5 truncate rounded-full border border-line bg-white px-2.5 py-1 text-xs font-medium text-ink-2" title={`Active organization: ${org.name}`}><span aria-hidden className="size-1.5 rounded-full bg-mint" />{org.name}</span>
      <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 text-sm md:flex">
        {crumbs.map((c, i) => (
          <React.Fragment key={`${c.label}-${i}`}>
            {i > 0 && <ChevronRight className="size-3.5 text-ink-3" />}
            {c.href && i < crumbs.length - 1 ? (
              <Link href={c.href} className="truncate text-ink-2 hover:text-ink">
                {c.label}
              </Link>
            ) : (
              <span className="truncate font-medium capitalize text-ink">{c.label}</span>
            )}
          </React.Fragment>
        ))}
      </nav>
      <LogoMark size={28} className="md:hidden" />

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={() => setCommand(true)}
          className="hidden h-10 w-64 items-center gap-2.5 rounded-xl border border-line bg-white px-3 text-left text-sm text-ink-3 transition-colors hover:border-violet/30 sm:flex lg:w-80"
          aria-label="Search or open command palette"
        >
          <Search className="size-4" />
          <span className="flex-1">Search anything…</span>
          <kbd className="rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[11px] font-medium text-ink-3">Ctrl K</kbd>
        </button>
        <button
          onClick={() => setCommand(true)}
          className="flex size-10 items-center justify-center rounded-xl border border-line bg-white text-ink-2 sm:hidden"
          aria-label="Search"
        >
          <Search className="size-[18px]" />
        </button>

        <Dropdown>
          <DropdownTrigger asChild>
            <Button variant="gradient" className="hidden sm:inline-flex">
              <Plus /> Create
            </Button>
          </DropdownTrigger>
          <DropdownContent className="w-60">
            <DropdownLabel>Quick create</DropdownLabel>
            {canAccess(role, "/devtrack/projects") && (!isLive()||["senior_developer","junior_developer"].includes(currentUser.role)) && <DropdownItem icon={<FolderPlus />} onSelect={() => router.push("/devtrack/projects?new=1")}>Project proposal</DropdownItem>}
            {canAccess(role, "/devtrack/board") && (!isLive()||currentUser.role==="senior_developer") && <DropdownItem icon={<ListPlus />} onSelect={() => router.push("/devtrack/board?new=1")}>Task</DropdownItem>}
            {canAccess(role, "/people/lifecycle") && <DropdownItem icon={<UserPlus />} onSelect={() => router.push("/people/lifecycle")}>Employee onboarding</DropdownItem>}
            {canAccess(role, "/devtrack/security") && <DropdownItem icon={<ScanSearch />} onSelect={() => router.push("/devtrack/security?scan=1")}>Repository scan</DropdownItem>}
          </DropdownContent>
        </Dropdown>

        <NotificationsPopover />

        <Dropdown>
          <DropdownTrigger asChild>
            <button className="rounded-full" aria-label="Profile menu">
              <Avatar src={currentUser.photo} name={currentUser.name} size={38} />
            </button>
          </DropdownTrigger>
          <DropdownContent className="w-60">
            <div className="px-2.5 py-2">
              <p className="text-sm font-semibold text-ink">{currentUser.name}</p>
              <p className="text-xs text-ink-3">{currentUser.email}</p>
            </div>
            <DropdownItem onSelect={() => router.push("/workspace/settings")}>Profile & security</DropdownItem>
            {canAccess(role, "/workspace/organization") && <DropdownItem onSelect={() => router.push("/workspace/organization")}>Organization</DropdownItem>}
            <DropdownItem onSelect={() => router.push("/workspace/help")}>Help & docs</DropdownItem>
            <DropdownItem danger onSelect={()=>{if(isLive())void logoutLive().finally(()=>{router.push("/login");router.refresh();});else endDemoSession();}}>Sign out</DropdownItem>
          </DropdownContent>
        </Dropdown>
      </div>
    </header>
  );
}
