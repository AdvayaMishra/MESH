import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Role } from "@/lib/types";

interface UIState {
  sidebarCollapsed: boolean;
  mobileNavOpen: boolean;
  commandOpen: boolean;
  /** Demo-mode role. Persisted per browser tab so a reload or deep link keeps the chosen role. */
  role: Role;
  /** True once persisted state has been read on the client (prevents a guard/hydration flash). */
  hydrated: boolean;
  toggleSidebar: () => void;
  setMobileNav: (o: boolean) => void;
  setCommand: (o: boolean) => void;
  setRole: (r: Role) => void;
}

export const useUI = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      mobileNavOpen: false,
      commandOpen: false,
      role: "owner",
      hydrated: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setMobileNav: (mobileNavOpen) => set({ mobileNavOpen }),
      setCommand: (commandOpen) => set({ commandOpen }),
      setRole: (role) => set({ role }),
    }),
    {
      name: "mesh-demo-ui",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({ role: s.role, sidebarCollapsed: s.sidebarCollapsed }),
      skipHydration: true, // rehydrated in <UIHydrator/> after mount to avoid SSR mismatch
      onRehydrateStorage: () => () => useUI.setState({ hydrated: true }),
    }
  )
);
