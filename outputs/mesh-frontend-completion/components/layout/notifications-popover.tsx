"use client";
import { useDataset } from "@/lib/api";
import Link from "next/link";
import { Popover } from "radix-ui";
import { Bell, CheckCheck } from "lucide-react";
import { useWorkspace } from "@/stores/workspace-store";
import { timeAgo } from "@/lib/utils/format";
import { useUI } from "@/stores/ui-store";
import { visibleNotification } from "@/lib/notifications";
import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";

const toneDot = { violet: "bg-violet", mint: "bg-mint", amber: "bg-amber", coral: "bg-coral", sky: "bg-sky" } as const;

export function NotificationsPopover() {
  const { notifications: allNotifications, markNotification, markAllNotifications } = useWorkspace();
  const role = useUI((s) => s.role);
  const { currentUser } = useDataset();
  const notifications = allNotifications.filter((n) => visibleNotification(n, role, currentUser.id));
  const unread = notifications.filter((n) => !n.read).length;
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          aria-label={`Notifications, ${unread} unread`}
          className="relative flex size-10 items-center justify-center rounded-xl border border-line bg-white text-ink-2 transition-colors hover:bg-tint-violet hover:text-indigo"
        >
          <Bell className="size-[18px]" />
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 flex size-[18px] items-center justify-center rounded-full bg-coral text-[10px] font-bold text-white ring-2 ring-canvas">
              {unread}
            </span>
          )}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={10}
          className="z-[60] w-[min(24rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border border-line bg-white shadow-pop data-[state=open]:animate-in data-[state=open]:fade-in data-[state=open]:slide-in-from-top-2"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="font-display text-sm font-semibold">Notifications</p>
            <Button size="sm" variant="ghost" onClick={markAllNotifications} disabled={!unread}>
              <CheckCheck /> Mark all read
            </Button>
          </div>
          <ul className="max-h-96 divide-y divide-line overflow-y-auto">
            {notifications.slice(0, 6).map((n) => (
              <li key={n.id}>
                <Link
                  href={n.href}
                  onClick={() => markNotification(n.id)}
                  className={cn("flex gap-3 px-4 py-3 transition-colors hover:bg-canvas", !n.read && "bg-tint-violet/40")}
                >
                  <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read ? "bg-line-strong" : toneDot[n.tone])} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium text-ink">{n.title}</span>
                    <span className="mt-0.5 block text-xs text-ink-2">{n.body}</span>
                    <span className="mt-1 block text-[11px] text-ink-3">
                      {n.module} · {timeAgo(n.at)}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <Link href="/workspace/notifications" className="block border-t border-line px-4 py-3 text-center text-[13px] font-medium text-indigo hover:bg-canvas">
            View all notifications
          </Link>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
