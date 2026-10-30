import { test, expect } from "@playwright/test";
import { asRole } from "./helpers";
async function navigate(page: import("@playwright/test").Page, href: string) {
  await page.locator(`nav[aria-label="Primary"] a[href="${href}"]`).click();
}
test("profile edits survive navigation and remain isolated by role", async ({ page }) => {
  await asRole(page, "owner"); await page.goto("/workspace/settings");
  await page.getByLabel("Full name", { exact: true }).fill("Updated Demo Owner");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.getByText("Demo profile saved for this session")).toBeVisible();
  await navigate(page, "/workspace/notifications");
  await page.getByRole("button", { name: "Profile menu" }).click();
  await expect(page.getByText("Updated Demo Owner").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "HR", exact: true }).click();
  await expect(page.getByText("Updated Demo Owner")).toHaveCount(0);
});
test("notifications do not expose HR or finance records to junior developers", async ({ page }) => {
  await asRole(page, "junior-dev"); await page.goto("/workspace/notifications");
  await expect(page.locator('main a[href^="/people"]')).toHaveCount(0);
  await expect(page.locator('main a[href^="/owner"]')).toHaveCount(0);
  await expect(page.locator('main a[href^="/vader"]')).toHaveCount(0);
  await page.getByRole("button", { name: /Notifications,.*unread/ }).click();
  await expect(page.locator('[data-radix-popper-content-wrapper] a[href^="/people"]')).toHaveCount(0);
});
test("owner creates an employee, allocates department budget and changes organization identity", async ({ page }) => {
  await asRole(page, "owner"); await page.goto("/people/administration");
  await page.getByLabel("Employee name", { exact: true }).fill("Demo Journey Person");
  await page.getByLabel("Employee email", { exact: true }).fill("journey@example.invalid");
  await page.getByLabel("Job title", { exact: true }).fill("Software Engineer");
  await page.getByRole("button", { name: "Create employee record", exact: true }).click();
  await expect(page.getByText("Onboarding record created in this demo session")).toBeVisible();
  await navigate(page, "/people/directory");
  await page.getByPlaceholder(/Search.*name|Search people/i).fill("Demo Journey Person");
  await expect(page.locator("main")).toContainText("journey@example.invalid");
  await navigate(page, "/owner");
  await expect(page.getByRole("region", {name:"Key metrics"}).getByText("24", {exact:true})).toBeVisible();
  await navigate(page, "/owner/finance");
  await page.getByLabel("Monthly budget (USD)", { exact: true }).fill("12345");
  await page.getByRole("button", { name: "Allocate budget", exact: true }).click();
  await expect(page.getByText("$12,345", { exact: true })).toBeVisible();
  await navigate(page, "/workspace/organization");
  await page.getByLabel("Name", { exact: true }).fill("Journey Organization");
  await page.getByLabel("Website", { exact: true }).fill("journey.example");
  await page.getByRole("button", { name: "Save organization", exact: true }).click();
  await expect(page.getByTestId("active-org")).toHaveText("Journey Organization");
  await page.getByRole("button", { name: /switch organization/i }).click();
  await page.getByRole("menuitem", { name: /Northwind Health Labs/i }).click();
  await expect(page.getByText("Journey Organization")).toHaveCount(0);
});
test("cloud remediation persists across navigation and can be reopened", async ({ page }) => {
  await asRole(page, "security-analyst"); await page.goto("/vader/cloud");
  await page.getByRole("button", { name: "Mark remediated", exact: true }).first().click();
  await expect(page.getByRole("button", { name: "Reopen", exact: true })).toHaveCount(1);
  await navigate(page, "/vader/incidents"); await navigate(page, "/vader/cloud");
  await page.getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(page.getByRole("button", { name: "Reopen", exact: true })).toHaveCount(0);
});
for (const width of [390, 768, 1440]) {
  test(`responsive ${width}: navigation and settings fit the viewport @mobile`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); await asRole(page, "owner");
    const errors: string[] = []; page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/workspace/settings"); await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: `test-results/settings-${width}-${test.info().project.name}.png`, fullPage: true });
    expect(errors).toEqual([]);
  });
}

test("lifecycle requires independent approval, updates directory state and supports reversal", async ({ page }) => {
  await asRole(page, "hr"); await page.goto("/people/lifecycle");
  await page.getByRole("button", { name: /Preview access changes/ }).click();
  await page.getByRole("button", { name: /Run simulation/ }).click();
  await page.getByRole("button", { name: /See reversal plan/ }).click();
  await page.getByRole("button", { name: "Save plan and request approvals" }).click();
  await expect(page.getByRole("button", { name: "Approve plan", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Owner", exact: true }).click();
  await page.getByRole("button", { name: "Approve plan", exact: true }).click();
  await page.getByRole("button", { name: "Execute in demo", exact: true }).click();
  await page.getByRole("button", { name: "Reverse demo changes", exact: true }).click();
  await expect(page.locator("main")).toContainText("Reversed");
});

test("identity preview requires HR review and activates the invited demo persona", async ({ page }) => {
  await asRole(page, "owner"); await page.goto("/invite/employee/id-upload");
  await page.getByLabel("Upload ID file").setInputFiles({ name: "synthetic-id.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64") });
  await page.getByRole("button", { name: "Submit for review", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Waiting for a human review" })).toBeVisible();
  await page.getByRole("button", { name: "Open demo reviewer workspace" }).click();
  await expect(page.getByRole("heading", { name: "Verification center" })).toBeVisible();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await page.getByRole("button", { name: "Approve ID", exact: true }).click();
  await page.getByRole("link", { name: "Return to invitation preview" }).click();
  await page.getByRole("button", { name: "Continue to activation" }).click();
  await page.getByRole("button", { name: "Activate and open workspace" }).click();
  await expect(page).toHaveURL(/\/devtrack$/);
  await page.getByRole("button", { name: "Profile menu" }).click();
  await expect(page.getByText("Yuki Tanaka").first()).toBeVisible();
});

test("security investigation notes and response reversal survive navigation", async ({ page }) => {
  await asRole(page, "security-analyst"); await page.goto("/vader/incidents/INC-3021");
  await page.getByLabel("Investigation note", { exact: true }).fill("Reviewed the correlated synthetic evidence and requested owner confirmation.");
  await page.getByRole("button", { name: "Add investigation note", exact: true }).click();
  await expect(page.getByText("Investigation note saved (demo)")).toBeVisible();
  await navigate(page, "/vader/incidents");
  await page.locator('main a[href="/vader/incidents/INC-3021"]').click();
  await expect(page.locator("main")).toContainText("Reviewed the correlated synthetic evidence");
  await page.getByRole("button", { name: "Review and approve", exact: true }).first().click();
  await page.getByLabel("Why are you approving this?", { exact: true }).fill("Approved response against synthetic evidence for this demo.");
  await page.getByRole("button", { name: "Approve (simulated)", exact: true }).click();
  await page.getByRole("button", { name: "Undo", exact: true }).first().click();
  await expect(page.getByText("Action reversed in the simulation")).toBeVisible();
});

test("payroll preparation requires discrepancy review and independent approval", async ({ page }) => {
  await asRole(page, "hr"); await page.goto("/people/payroll");
  await page.getByRole("button", { name: "Prepare payroll run", exact: true }).click();
  await expect(page.getByText("Review every payroll discrepancy before preparing the run.")).toBeVisible();
  while (await page.getByRole("button", { name: "Mark reviewed", exact: true }).count()) await page.getByRole("button", { name: "Mark reviewed", exact: true }).first().click();
  await page.getByRole("button", { name: "Prepare payroll run", exact: true }).click();
  await expect(page.getByRole("button", { name: "Approve payroll run", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Account menu" }).click(); await page.getByRole("menuitem", { name: "Owner", exact: true }).click();
  await page.getByRole("button", { name: "Approve payroll run", exact: true }).click();
  await expect(page.getByText("Demo payroll approved; no payment sent")).toBeVisible();
});

test("profile photo validates format and can be removed", async ({ page }) => {
  await asRole(page, "owner"); await page.goto("/workspace/settings");
  await page.getByLabel("Upload profile photo", { exact: true }).setInputFiles({name:"bad.txt",mimeType:"text/plain",buffer:Buffer.from("not an image")});
  await expect(page.getByText("Choose a PNG, JPEG or WebP image up to 2 MB.")).toBeVisible();
  const data = await page.evaluate(() => { const canvas=document.createElement("canvas"); canvas.width=2;canvas.height=2;canvas.getContext("2d")!.fillRect(0,0,2,2);return canvas.toDataURL("image/png").split(",")[1]; });
  await page.getByLabel("Upload profile photo", { exact: true }).setInputFiles({name:"demo.png",mimeType:"image/png",buffer:Buffer.from(data,"base64")});
  await page.getByRole("button", { name: "Remove photo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove photo", exact: true })).toHaveCount(0);
});

test("developer creates, edits, comments on and deletes a task", async ({ page }) => {
  await asRole(page, "senior-dev"); await page.goto("/devtrack/board");
  await page.getByRole("button", { name: "New task", exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill("Browser workflow task");
  await page.getByLabel("Description", { exact: true }).fill("Synthetic task for the complete browser workflow.");
  await page.getByLabel("Due date", { exact: true }).fill("2027-02-15");
  await page.getByRole("button", { name: "Create task", exact: true }).click();
  await page.getByLabel("Search tasks", { exact: true }).fill("Browser workflow task");
  await page.getByRole("button", { name: /Open .*Browser workflow task/ }).click();
  await page.getByRole("button", { name: "Edit task details", exact: true }).click();
  await page.getByLabel("Edit task title", { exact: true }).fill("Browser workflow task updated");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Browser workflow task updated", exact: true })).toBeVisible();
  await page.getByLabel("Write a comment", { exact: true }).fill("Reviewed the implementation and acceptance criteria.");
  await page.getByRole("button", { name: "Send comment", exact: true }).click();
  await expect(page.getByText("Reviewed the implementation and acceptance criteria.")).toBeVisible();
  await page.getByRole("button", { name: "Delete task", exact: true }).click();
  await page.getByRole("dialog").filter({has:page.getByRole("heading",{name:"Delete this demo task?",exact:true})}).getByRole("button",{name:"Delete task",exact:true}).click();
  await expect(page.getByRole("button", { name: /Open .*Browser workflow task/ })).toHaveCount(0);
});

test("free-text planning and copilot answers are grounded and labeled", async ({ page }) => {
  await asRole(page, "owner"); await page.goto("/owner/finance");
  await page.getByLabel("Ask a what-if question", { exact: true }).fill("Reduce cloud spend by 15%");
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(page.getByText(/arithmetic on seeded forecasts/)).toBeVisible({timeout:15000});
  await navigate(page,"/vader/copilot");
  await page.getByLabel("Ask the Copilot",{exact:true}).fill("Explain INC-3021");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.locator('main a[href="/vader/incidents/INC-3021"]')).toBeVisible({timeout:15000});
  await expect(page.getByText("Simulated AI", {exact:true})).toBeVisible();
});

test("reports export real CSV/XLSX and a printable PDF view with date filtering", async ({ page }) => {
  await asRole(page,"owner"); await page.goto("/workspace/reports");
  const exportCloud = () => page.getByRole("heading",{name:"Monthly cloud spend",exact:true}).locator("..").getByRole("button",{name:"Export",exact:true}).click();
  await exportCloud();
  const csvEvent = page.waitForEvent("download");
  await page.getByRole("button",{name:"Generate",exact:true}).click();
  const csv = await csvEvent; expect(csv.suggestedFilename()).toBe("mesh-r1-demo.csv"); await csv.saveAs("test-results/demo-report.csv");
  await exportCloud(); await page.getByLabel("Export format",{exact:true}).selectOption("xlsx");
  const workbookEvent = page.waitForEvent("download");
  await page.getByRole("button",{name:"Generate",exact:true}).click();
  const workbook = await workbookEvent; expect(workbook.suggestedFilename()).toBe("mesh-r1-demo.xlsx"); await workbook.saveAs("test-results/demo-report.xlsx");
  await exportCloud(); await page.getByLabel("Export format",{exact:true}).selectOption("print");
  const popupEvent=page.waitForEvent("popup"); await page.getByRole("button",{name:"Generate",exact:true}).click();
  const popup=await popupEvent; await expect(popup.getByRole("heading",{name:/Monthly cloud spend/})).toBeVisible();
  await expect(popup.getByRole("button",{name:"Print / save PDF",exact:true})).toBeVisible();
  const pdf=await popup.pdf({path:"test-results/demo-report.pdf",format:"A4"}); expect(pdf.subarray(0,4).toString()).toBe("%PDF"); await popup.close();
  await page.getByRole("heading",{name:"Incident security summary",exact:true}).locator("..").getByRole("button",{name:"Export",exact:true}).click();
  await page.getByLabel("Export format",{exact:true}).selectOption("csv");
  await page.getByLabel("From date",{exact:true}).fill("2099-01-01");
  await page.getByRole("button",{name:"Generate",exact:true}).click();
  await expect(page.getByText("No records match the selected report and date range.")).toBeVisible();
});

test("HR invitation enters the HR persona with the accepted display name", async ({ page }) => {
  await asRole(page,"owner");await page.goto("/invite/hr");
  await page.getByLabel("Full name",{exact:true}).fill("Browser HR preview");
  await page.getByLabel("Create a password",{exact:true}).fill("SyntheticPreview-42!");
  await page.getByRole("checkbox").check();
  await page.getByRole("button",{name:"Accept and go to People",exact:true}).click();
  await expect(page).toHaveURL(/\/people$/);
  await page.getByRole("button",{name:"Profile menu"}).click();
  await expect(page.getByText("Browser HR preview").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("navigation",{name:"Primary"}).getByText("MESH Owner",{exact:true})).toHaveCount(0);
});

test("owner onboarding opens an explicitly seeded owner example", async ({ page }) => {
  await asRole(page,"junior-dev");await page.goto("/register/pending");
  await page.getByRole("button",{name:"Open example dashboard",exact:true}).click();
  await expect(page).toHaveURL(/\/owner$/);
  await expect(page.getByRole("navigation",{name:"Primary"}).getByText("MESH Owner",{exact:true})).toBeVisible();
});

test("demo sign-out clears private profile state", async ({ page }) => {
  await asRole(page,"owner");await page.goto("/workspace/settings");
  await page.getByLabel("Full name",{exact:true}).fill("Private session profile");
  await page.getByRole("button",{name:"Save profile",exact:true}).click();
  await page.getByRole("button",{name:"Profile menu"}).click();
  await page.getByRole("menuitem",{name:"Sign out",exact:true}).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/workspace/settings");
  await expect(page.getByLabel("Full name",{exact:true})).toHaveValue("Alex Morgan");
});
