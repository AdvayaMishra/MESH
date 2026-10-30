"use client";
import * as React from "react";
import { scoreFromEvents } from "@/lib/trust";
import { useWorkspace } from "@/stores/workspace-store";
import type { Employee, TrustEvent } from "@/lib/types";

/** Effective Trust score + history for an employee: seeded history plus reviewed events recorded in this session. */
export function useTrust(e: Employee | null | undefined): { eligible: boolean; score: number | null; events: TrustEvent[] } {
  const extra = useWorkspace((s) => (e ? s.trustEvents[e.id] : undefined));
  return React.useMemo(() => {
    if (!e || e.trustScore === null) return { eligible: false, score: null, events: [] };
    const events = [...(extra ?? []), ...e.trustEvents];
    return { eligible: true, score: scoreFromEvents(events), events };
  }, [e, extra]);
}
