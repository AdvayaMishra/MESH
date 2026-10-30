"use client";
import {isLive,useLive,displayRole} from "@/lib/connected/live-state";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { canAccess, roleHome, ruleFor } from "@/lib/permissions";
import { roleLabels } from "@/lib/nav";
import { useUI } from "@/stores/ui-store";
import { useWorkspace } from "@/stores/workspace-store";
import { useTenant } from "@/stores/tenant-store";
import { usePreferences } from "@/stores/preferences-store";

/** Reads persisted demo state once after mount. */
export function UIHydrator() {
  React.useEffect(() => {
    // Restore the demo tenant first so the workspace slice matches it before any page renders.
    void Promise.resolve(useTenant.persist.rehydrate()).then(() => {
      useWorkspace.getState().switchOrg(useTenant.getState().orgId);
      return useUI.persist.rehydrate();
    });
  }, []);
  return null;
}

function AccessDenied({ pathname }: { pathname: string }) {
  const role = useUI((s) => s.role);
  const log = useWorkspace((s) => s.log);
  const rule = ruleFor(pathname);
  const allowed = rule?.roles.map((r) => roleLabels[r]).join(", ") ?? roleLabels.owner;

  // Record the denied attempt once per path/role in the (simulated) audit log.
  const logged = React.useRef("");
  React.useEffect(() => {
    const key = `${role}:${pathname}`;
    if (logged.current === key) return;
    logged.current = key;
    log({ actor: roleLabels[role], action: "Blocked navigation (route guard)", target: pathname, module: "System", result: "Denied" });
  }, [log, pathname, role]);

  return (
    <section role="alert" aria-labelledby="denied-title" className="mx-auto mt-10 max-w-lg rounded-3xl border border-line bg-white p-8 text-center shadow-card sm:mt-16 sm:p-10">
      <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-tint-coral text-coral">
        <LockKeyhole className="size-6" aria-hidden />
      </span>
      <h1 id="denied-title" className="mt-5 font-display text-xl font-semibold text-ink">Access denied</h1>
      <p className="mt-2 text-sm text-ink-2">
        Your current role, <strong className="text-ink">{roleLabels[role]}</strong>, can&apos;t open this page.
        {rule?.note ? ` ${rule.note}` : ""}
      </p>
      <p className="mt-3 text-xs text-ink-3">Roles with access: {allowed}</p>
      <div className="mt-6 flex flex-col justify-center gap-2 sm:flex-row">
        <Button asChild variant="gradient"><Link href={roleHome[role]}>Go to my home</Link></Button>
        <Button asChild variant="secondary"><Link href="/workspace/help">Request access</Link></Button>
      </div>
      <p className="mt-6 rounded-xl bg-canvas px-3 py-2 text-left text-xs text-ink-3">
        Navigation is filtered for your role. The backend independently checks membership, permissions and organization access for every request.
      </p>
    </section>
  );
}

export function RouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const ui = useUI();
  const profile=useLive(s=>s.profile);
  const role=isLive()&&profile?displayRole[profile.role]:ui.role;
  const hydrated=ui.hydrated;
  const orgId = useTenant((s) => s.orgId);
  const persona = usePreferences((s) => s.personas[orgId]?.[role]);

  if (!hydrated) {
    return (
      <div aria-busy="true" aria-label="Loading" className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!canAccess(role, pathname)) return <AccessDenied pathname={pathname} />;
  // Remount page subtrees when the tenant or demo identity changes so no local state from the previous tenant survives.
  return <React.Fragment key={`${orgId}:${role}:${persona ?? "default"}`}>{children}</React.Fragment>;
}
