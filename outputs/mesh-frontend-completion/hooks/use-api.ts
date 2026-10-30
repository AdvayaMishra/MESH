"use client";
import { useLive } from "@/lib/connected/live-state";
import * as React from "react";
import { useAdministration } from "@/stores/admin-store";
import { useTenant } from "@/stores/tenant-store";

/** Minimal data hook with loading state so every screen can render skeletons. Fetches once on mount. */
export function useApi<T>(fetcher: () => Promise<T>) {
  const liveRevision=useLive(s=>s.revision);
  const revision = useAdministration((s) => s.revision);
  const orgId = useTenant((s) => s.orgId);
  const [state, setState] = React.useState<{ orgId: string; data: T | null; loading: boolean; error: string | null }>({ orgId, data: null, loading: true, error: null });
  const fetchCurrent = React.useEffectEvent(() => fetcher());

  React.useEffect(() => {
    let alive = true;
    fetchCurrent()
      .then((data) => alive && setState({ orgId, data, loading: false, error: null }))
      .catch((e: unknown) => alive && setState({ orgId, data: null, loading: false, error: e instanceof Error ? e.message : "Something went wrong" }));
    return () => {
      alive = false;
    };
  }, [orgId, revision, liveRevision]);

  return state.orgId === orgId ? state : { data: null, loading: true, error: null };
}
