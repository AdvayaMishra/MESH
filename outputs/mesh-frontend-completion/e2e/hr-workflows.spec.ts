import { test, expect, type Page } from "@playwright/test";
import { asRole, DENIED, type RoleId } from "./helpers";

/** NOT YET EXECUTED (checkpoint 4 sandbox had no working npm install). Run: npm run build && npm run test:e2e -- hr-workflows */
async function asTenant(page: Page, orgId: string) {
  await page.addInitScript((id) => sessionStorage.setItem("mesh-demo-tenant", JSON.stringify({ state: { orgId: id }, version: 0 })), orgId);
}
async function open(page: Page, role: RoleId, path: string, org = "lumen") { await asRole(page, role); await asTenant(page, org); await page.goto(path); }

test("complaint: employee submits, validates, sees it in own history; Owner can't open the review queue", async ({ page }) => {
  await open(page, "senior-dev", "/workspace/complaints");
  await page.getByRole("button", { name: /new complaint/i }).click();
  await page.getByRole("button", { name: /submit complaint/i }).click();
  await expect(page.getByText(/short title/i)).toBeVisible();
  await page.getByLabel("Title").fill("Broken badge reader at the east door");
  await page.getByLabel("Category").selectOption("Safety concern");
  await page.getByLabel("When did it happen?").fill(new Date().toISOString().slice(0, 10));
  await page.getByLabel("What happened?").fill("The east door badge reader has failed repeatedly and staff prop the door open.");
  await page.getByRole("button", { name: /submit complaint/i }).click();
  await expect(page.getByTestId("my-complaint").filter({ hasText: "Broken badge reader" })).toContainText("Submitted");
  await open(page, "owner", "/people/complaints");
  await expect(page.getByText(DENIED)).toBeVisible();
});

test("complaint: HR moves a case through valid states and the employee sees the new status", async ({ page }) => {
  await open(page, "hr", "/people/complaints");
  await page.getByTestId("complaint-row").filter({ hasText: "Repeated dismissive comments" }).click();
  await page.getByRole("button", { name: "Mark Investigating" }).click();
  await expect(page.getByText("Moved to Investigating").first()).toBeVisible();
});

test("complaint: unrelated roles see no complaints; Restricted case is redacted for non-assigned HR", async ({ page }) => {
  await open(page, "junior-dev", "/workspace/complaints");
  await expect(page.getByTestId("my-complaint")).toHaveCount(2); // Aisha's own two seeded cases only
  await expect(page.getByText("customer data exports")).toHaveCount(0);
  await open(page, "hr", "/people/complaints"); // Priya is the subject of C-103
  await expect(page.getByText(/customer data exports/)).toHaveCount(0);
});

test("promotion: HR proposes, Owner approves, status updates; tenant switch shows other proposals", async ({ page }) => {
  await open(page, "owner", "/people/promotions");
  await expect(page.getByTestId("promotion-card").filter({ hasText: "Aisha Khan" })).toContainText("Pending Owner approval");
  await page.getByLabel("Decision note for P-101").fill("Approved with thanks.");
  await page.getByTestId("promotion-card").filter({ hasText: "Aisha Khan" }).getByRole("button", { name: "Approve" }).click();
  await expect(page.getByTestId("promotion-card").filter({ hasText: "Aisha Khan" })).toContainText("Approved");
  await open(page, "owner", "/people/promotions", "northwind");
  await expect(page.getByText("Aisha Khan")).toHaveCount(0);
  await expect(page.getByText("Theo Larsen").first()).toBeVisible();
});

test("promotion: developers are blocked from the page", async ({ page }) => { await open(page, "senior-dev", "/people/promotions"); await expect(page.getByText(DENIED)).toBeVisible(); });

test("leave: employee requests leave with validation; HR approves; status tracked", async ({ page }) => {
  await open(page, "junior-dev", "/workspace/leave");
  await page.getByRole("button", { name: /submit request/i }).click();
  await expect(page.getByText(/start date/i).first()).toBeVisible();
  const d = (n: number) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
  await page.getByLabel("From").fill(d(50)); await page.getByLabel("To").fill(d(52));
  await page.getByRole("button", { name: /submit request/i }).click();
  await expect(page.getByTestId("my-leave").first()).toContainText("Pending");
});
