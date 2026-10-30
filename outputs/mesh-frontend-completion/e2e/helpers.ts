import type { Page } from "@playwright/test";

export type RoleId = "owner" | "hr" | "senior-dev" | "junior-dev" | "security-analyst";

/** Seeds the demo role before the app boots (mirrors what the role switcher persists). */
export async function asRole(page: Page, role: RoleId) {
  await page.addInitScript((r) => {
    sessionStorage.setItem("mesh-demo-ui", JSON.stringify({ state: { role: r, sidebarCollapsed: false }, version: 0 }));
  }, role);
}

export const DENIED = /access denied/i;
