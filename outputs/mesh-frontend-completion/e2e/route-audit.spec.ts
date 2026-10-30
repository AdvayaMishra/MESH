import { test, expect } from "@playwright/test";
import { asRole, type RoleId } from "./helpers";
const routes: [string, RoleId][] = [["/forgot-password", "owner"], ["/invite/employee/activate", "owner"], ["/invite/employee/id-upload", "owner"], ["/invite/employee", "owner"], ["/invite/employee/pending", "owner"], ["/invite/hr", "owner"], ["/login", "owner"], ["/register/dns", "owner"], ["/register/organization", "owner"], ["/register", "owner"], ["/register/pending", "owner"], ["/register/verify", "owner"], ["/register/website", "owner"], ["/reset-password", "owner"], ["/devtrack/board", "owner"], ["/devtrack", "owner"], ["/devtrack/projects", "owner"], ["/devtrack/pull-requests", "owner"], ["/devtrack/security", "owner"], ["/devtrack/sprints", "owner"], ["/owner/finance", "owner"], ["/owner", "owner"], ["/owner/performance", "owner"], ["/owner/projects", "owner"], ["/people/administration", "owner"], ["/people/complaints", "hr"], ["/people/directory", "owner"], ["/people/leave", "owner"], ["/people/leave/review", "owner"], ["/people/lifecycle", "owner"], ["/people", "owner"], ["/people/payroll", "owner"], ["/people/promotions", "owner"], ["/people/verification", "owner"], ["/vader/attack-chain", "owner"], ["/vader/behavior", "owner"], ["/vader/cloud", "owner"], ["/vader/copilot", "owner"], ["/vader/incidents", "owner"], ["/vader", "owner"], ["/vader/risk", "owner"], ["/vader/simulation", "owner"], ["/workspace/activity", "owner"], ["/workspace/audit", "owner"], ["/workspace/complaints", "owner"], ["/workspace/help", "owner"], ["/workspace/leave", "owner"], ["/workspace/notifications", "owner"], ["/workspace/organization", "owner"], ["/workspace", "owner"], ["/workspace/reports", "owner"], ["/workspace/settings", "owner"], ["/", "owner"]];
for (const [route, role] of routes) {
  test(`route audit ${route}: loads without runtime exceptions`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await asRole(page, role);
    const response = await page.goto(route);
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator("h1").first()).toBeVisible();
    await page.waitForTimeout(400);
    expect(errors).toEqual([]);
    expect(await page.locator("body").innerText()).not.toContain("Application error");
  });
}
