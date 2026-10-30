"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import { Dialog as D } from "radix-ui";
import { CornerDownLeft, FolderKanban, Search, ShieldAlert, Users, Zap } from "lucide-react";
import { sections } from "@/lib/nav";
import { useUI } from "@/stores/ui-store";
import { canAccess } from "@/lib/permissions";
import { useDataset } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace-store";

export function CommandPalette() {
  const { employees } = useDataset();
  // Search the active tenant's current working state, not the original seed.
  const projects = useWorkspace((s) => s.projects);
  const incidents = useWorkspace((s) => s.incidents);
  const { commandOpen, setCommand, role } = useUI();
  const can = (href: string) => canAccess(role, href);
  const router = useRouter();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommand(!useUI.getState().commandOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCommand]);

  const go = (href: string) => {
    setCommand(false);
    router.push(href);
  };

  const itemCls =
    "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-ink aria-selected:bg-tint-violet [&_svg]:size-4 [&_svg]:text-ink-3 aria-selected:[&_svg]:text-violet";
  const groupCls = "px-1 pb-2 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-ink-3";

  return (
    <D.Root open={commandOpen} onOpenChange={setCommand}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[80] bg-[#172033]/35 backdrop-blur-[2px]" />
        <D.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[12vh] z-[90] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-white shadow-pop focus:outline-none"
        >
          <D.Title className="sr-only">Command palette</D.Title>
          <Command label="Command palette" loop>
            <div className="flex items-center gap-3 border-b border-line px-4">
              <Search className="size-4 text-ink-3" />
              <Command.Input
                autoFocus
                placeholder="Search people, projects, incidents, or jump to a page…"
                className="h-14 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-3"
              />
              <kbd className="rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[11px] text-ink-3">Esc</kbd>
            </div>
            <Command.List className="max-h-[56vh] overflow-y-auto p-2">
              <Command.Empty className="px-4 py-10 text-center text-sm text-ink-2">No matches. Try a name, project key, or incident ID.</Command.Empty>
              <Command.Group heading="Quick actions" className={groupCls}>
                {can("/devtrack/projects") && (
                  <Command.Item className={itemCls} onSelect={() => go("/devtrack/projects?new=1")}>
                    <Zap /> Propose a project
                  </Command.Item>
                )}
                {can("/devtrack/security") && (
                  <Command.Item className={itemCls} onSelect={() => go("/devtrack/security?scan=1")}>
                    <Zap /> Run a repository scan
                  </Command.Item>
                )}
                {can("/workspace/reports") && <Command.Item className={itemCls} onSelect={() => go("/workspace/reports")}><Zap /> Generate weekly report</Command.Item>}
              </Command.Group>
              {sections.map((s) => ({ ...s, items: s.items.filter((i) => can(i.href)) })).filter((s) => s.items.length > 0).map((s) => (
                <Command.Group key={s.id} heading={s.label} className={groupCls}>
                  {s.items.map((i) => (
                    <Command.Item key={i.href} value={`${s.label} ${i.label}`} className={itemCls} onSelect={() => go(i.href)}>
                      <i.icon /> {i.label}
                      <CornerDownLeft className="ml-auto opacity-0 aria-selected:opacity-100" />
                    </Command.Item>
                  ))}
                </Command.Group>
              ))}
              {can("/people/directory") && <Command.Group heading="People" className={groupCls}>
                {employees.map((e) => (
                  <Command.Item key={e.id} value={`${e.name} ${e.id} ${e.role}`} className={itemCls} onSelect={() => go(`/people/directory/${e.id}`)}>
                    <Users /> {e.name}
                    <span className="ml-auto text-xs text-ink-3">{e.role}</span>
                  </Command.Item>
                ))}
              </Command.Group>}
              {can("/devtrack/projects") && <Command.Group heading="Projects" className={groupCls}>
                {projects.map((p) => (
                  <Command.Item key={p.id} value={`${p.name} ${p.key}`} className={itemCls} onSelect={() => go(`/devtrack/projects/${p.id}`)}>
                    <FolderKanban /> {p.name}
                    <span className="ml-auto text-xs text-ink-3">{p.key}</span>
                  </Command.Item>
                ))}
              </Command.Group>}
              {can("/vader/incidents") && <Command.Group heading="Incidents" className={groupCls}>
                {incidents.map((i) => (
                  <Command.Item key={i.id} value={`${i.id} ${i.title}`} className={itemCls} onSelect={() => go(`/vader/incidents/${i.id}`)}>
                    <ShieldAlert /> <span className="truncate">{i.title}</span>
                    <span className="ml-auto text-xs text-ink-3">{i.id}</span>
                  </Command.Item>
                ))}
              </Command.Group>}
            </Command.List>
          </Command>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
