import { test, expect } from "@playwright/test";
import { asRole, DENIED, type RoleId } from "./helpers";

/** Independent oracle: expected access, written by hand (NOT derived from lib/permissions). */
const matrix: Record<string, Record<RoleId, boolean>> = {
  "/owner":                  { owner: true,  hr: false, "senior-dev": false, "junior-dev": false, "security-analyst": false },
  "/owner/finance":          { owner: true,  hr: false, "senior-dev": false, "junior-dev": false, "security-analyst": false },
  "/people":                 { owner: true,  hr: true,  "senior-dev": false, "junior-dev": false, "security-analyst": false },
  "/people/directory/LR-1010": { owner: true, hr: true, "senior-dev": false, "junior-dev": false, "security-analyst": false },
  "/people/payroll":         { owner: true,  hr: true,  "senior-dev": false, "junior-dev": false, "security-analyst": false },
  "/devtrack":               { owner: true,  hr: false, "senior-dev": true,  "junior-dev": true,  "security-analyst": true },
  "/devtrack/security":      { owner: true,  hr: false, "senior-dev": true,  "junior-dev": true,  "security-analyst": true },
  "/vader":                  { owner: true,  hr: false, "senior-dev": false, "junior-dev": false, "security-analyst": true },
  "/vader/incidents/INC-3021": { owner: true, hr: false, "senior-dev": false, "junior-dev": false, "security-analyst": true },
  "/workspace/settings":     { owner: true,  hr: true,  "senior-dev": true,  "junior-dev": true,  "security-analyst": true },
  "/workspace/reports":      { owner: true,  hr: true,  "senior-dev": true,  "junior-dev": false, "security-analyst": true },
  "/workspace/audit":        { owner: true,  hr: false, "senior-dev": false, "junior-dev": false, "security-analyst": true },
  "/workspace/organization": { owner: true,  hr: true,  "senior-dev": false, "junior-dev": false, "security-analyst": false },
};

for (const [path, roles] of Object.entries(matrix)) {
  for (const [role, allowed] of Object.entries(roles) as [RoleId, boolean][]) {
    test(`guard: ${role} ${allowed ? "can" : "cannot"} open ${path}`, async ({ page }) => {
      await asRole(page, role);
      await page.goto(path);
      const denied = page.getByRole("alert").filter({ hasText: DENIED });
      if (allowed) {
        await expect(page.locator("main h1").first()).toBeVisible();
        await expect(denied).toHaveCount(0);
      } else {
        await expect(denied).toBeVisible();
        await expect(page.getByRole("link", { name: /go to my home/i })).toBeVisible();
      }
    });
  }
}

test("guard: denied page does not leak the restricted page's content", async ({ page }) => {
  await asRole(page, "junior-dev");
  await page.goto("/owner/finance");
  await expect(page.getByRole("alert", { name: "Access denied" })).toBeVisible();
  await expect(page.getByText(/cloud spend/i)).toHaveCount(0);
});

test("guard: 'Go to my home' lands on the role's home", async ({ page }) => {
  await asRole(page, "hr");
  await page.goto("/vader");
  await page.getByRole("link", { name: /go to my home/i }).click();
  await expect(page).toHaveURL(/\/people$/);
});

test("role switch: updates sidebar and leaves a page the new role cannot open", async ({ page }) => {
  await asRole(page, "owner");
  await page.goto("/owner/finance");
  await expect(page.getByRole("navigation", { name: "Primary" }).getByText("MESH Owner")).toBeVisible();
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Junior Developer" }).click();
  await expect(page).toHaveURL(/\/devtrack$/);
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav.getByText("MESH Owner")).toHaveCount(0);
  await expect(nav.getByText("VADER")).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Audit log" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Board", exact: true })).toBeVisible();
});

test("role switch: choice persists across a full page load and is still enforced", async ({ page }) => {
  // No seeded role: start from the default (owner), switch through the real UI, then hard-navigate.
  await page.goto("/devtrack");
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Junior Developer" }).click();
  await expect(page.getByText("Junior Developer view")).toBeVisible();
  await page.goto("/owner"); // full document load, new JS context
  await expect(page.getByRole("alert").filter({ hasText: DENIED })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("alert").filter({ hasText: DENIED })).toBeVisible();
});

test("breadcrumb: /workspace crumb resolves (no 404)", async ({ page }) => {
  const notFound: string[] = [];
  page.on("response", (r) => { if (r.status() === 404) notFound.push(r.url()); });
  await asRole(page, "owner");
  await page.goto("/workspace/help");
  await page.waitForTimeout(1200);
  expect(notFound).toEqual([]);
  await page.goto("/workspace");
  await expect(page).toHaveURL(/\/workspace\/notifications$/);
});
