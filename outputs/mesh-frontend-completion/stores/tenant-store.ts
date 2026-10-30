import { isLive } from "@/lib/connected/live-state";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { DEFAULT_ORG_ID, tenants } from "@/lib/api/mock";

interface TenantState {
  /** Active simulated organization. Demo-only; the real backend derives the tenant from the authenticated session. */
  orgId: string;
  setOrg: (id: string) => void;
}

export const useTenant = create<TenantState>()(
  persist((set) => ({ orgId: DEFAULT_ORG_ID, setOrg: (orgId) => { if (isLive() ? !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(orgId) : !tenants[orgId]) throw new Error("Invalid organization"); set({ orgId }); } }), {
    name: "mesh-demo-tenant",
    storage: createJSONStorage(() => sessionStorage),
    skipHydration: true,
    merge: (persisted, current) => {
      const candidate = persisted && typeof persisted === "object" && "orgId" in persisted ? persisted.orgId : undefined;
      return { ...current, orgId: typeof candidate === "string" && tenants[candidate] ? candidate : DEFAULT_ORG_ID };
    },
  })
);
