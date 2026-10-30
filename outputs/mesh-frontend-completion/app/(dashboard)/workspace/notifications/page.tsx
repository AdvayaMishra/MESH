"use client";
import { useDataset } from "@/lib/api";
import * as React from "react";
import Link from "next/link";
import { CheckCheck } from "lucide-react";
import { PageHeader } from "@/components/features/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/stores/workspace-store";
import { timeAgo } from "@/lib/utils/format";
import { useUI } from "@/stores/ui-store";
import { visibleNotification } from "@/lib/notifications";
import { cn } from "@/lib/utils/cn";

const dot = { violet: "bg-violet", mint: "bg-mint", amber: "bg-amber", coral: "bg-coral", sky: "bg-sky" } as const;

export default function NotificationsPage() {
  const { notifications: allNotifications, markNotification, markAllNotifications } = useWorkspace();
  const role = useUI((s) => s.role);
  const { currentUser } = useDataset();
  const notifications = allNotifications.filter((n) => visibleNotification(n, role, currentUser.id));
  const [tab, setTab] = React.useState("all");
  const list = notifications.filter((n) => tab === "all" || (tab === "unread" ? !n.read : n.module.toLowerCase() === tab));
  return (
    <div>
      <PageHeader title="Notifications" description="Approvals, incidents and reviews in one place." actions={<Button variant="secondary" onClick={markAllNotifications}><CheckCheck /> Mark all read</Button>} />
      <Tabs value={tab} onValueChange={setTab}><TabsList>{["all", "unread", "owner", "people", "devtrack", "vader"].map((t) => <TabsTrigger key={t} value={t} className="capitalize">{t === "devtrack" ? "DevTrack" : t === "vader" ? "VADER" : t}</TabsTrigger>)}</TabsList></Tabs>
      <Card className="mt-4 divide-y divide-line">
        {list.length === 0 && <EmptyState title="Nothing here" description="You're all caught up." />}
        {list.map((n) => (
          <div key={n.id} className={cn("flex items-start gap-4 p-4", !n.read && "bg-tint-violet/40")}>
            <span className={cn("mt-2 size-2.5 shrink-0 rounded-full", n.read ? "bg-line-strong" : dot[n.tone])} />
            <div className="min-w-0 flex-1"><Link href={n.href} onClick={() => markNotification(n.id)} className="text-sm font-semibold hover:text-indigo">{n.title}</Link><p className="mt-0.5 text-[13px] text-ink-2">{n.body}</p><p className="mt-1 flex items-center gap-2 text-xs text-ink-3"><Badge tone="neutral">{n.module}</Badge>{timeAgo(n.at)}</p></div>
            <Button size="sm" variant="ghost" onClick={() => markNotification(n.id, !n.read)}>{n.read ? "Mark unread" : "Mark read"}</Button>
          </div>
        ))}
      </Card>
    </div>
  );
}
