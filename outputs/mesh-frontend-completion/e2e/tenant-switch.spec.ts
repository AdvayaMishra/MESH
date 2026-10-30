import { test, expect } from "@playwright/test";
import { asRole, type RoleId } from "./helpers";

/** NOTE: written in checkpoint 3 but NOT yet executed (no npm network in that session). Run `npm run build && npm run test:e2e`. */

async function asTenant(page: import("@playwright/test").Page, orgId: string) {
  await page.addInitScript((id) => {
    sessionStorage.setItem("mesh-demo-tenant", JSON.stringify({ state: { orgId: id }, version: 0 }));
  }, orgId);
}

test("tenant: active organization is shown and switching changes the displayed data", async ({ page }) => {
  await asRole(page, "owner");
  await page.goto("/devtrack/projects");
  await expect(page.getByTestId("active-org")).toContainText("Lumen Robotics");
  await expect(page.getByText("Atlas Fleet Console").first()).toBeVisible();

  await page.getByRole("button", { name: /switch organization/i }).click();
  await page.getByRole("menuitem", { name: /Northwind Health Labs/i }).click();

  await expect(page.getByTestId("active-org")).toContainText("Northwind Health Labs");
  await page.goto("/devtrack/projects");
  await expect(page.getByText("CareLink Patient Portal").first()).toBeVisible();
  await expect(page.getByText("Atlas Fleet Console")).toHaveCount(0);
});

test("tenant: Northwind shows its own people and none of Lumen's", async ({ page }) => {
  await asRole(page, "hr");
  await asTenant(page, "northwind");
  await page.goto("/people/directory");
  await expect(page.getByTestId("active-org")).toContainText("Northwind Health Labs");
  await expect(page.getByText("Rebecca Thornton").first()).toBeVisible();
  await expect(page.getByText("Alex Morgan")).toHaveCount(0);
  await expect(page.getByText("lumenrobotics.io")).toHaveCount(0);
});

for (const role of ["owner", "junior-dev", "security-analyst"] as RoleId[]) {
  test(`tenant: ${role} in Northwind sees no Lumen incident or project names`, async ({ page }) => {
    await asRole(page, role);
    await asTenant(page, "northwind");
    await page.goto(role === "security-analyst" || role === "owner" ? "/vader" : "/devtrack");
    await expect(page.locator("main h1").first()).toBeVisible();
    const body = await page.locator("main").innerText();
    for (const leak of ["INC-3021", "svc-reporting", "Atlas Fleet", "Lumen Robotics", "Alex Morgan"]) expect(body).not.toContain(leak);
  });
}
