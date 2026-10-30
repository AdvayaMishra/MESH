import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
test.beforeEach(async({page})=>{await page.route("https://challenges.cloudflare.com/**",route=>route.fulfill({contentType:"application/javascript",body:"window.turnstile={render:(el,o)=>{el.textContent='Synthetic browser-test challenge';setTimeout(()=>o.callback('fixture-only'),0);return 'fixture';},remove:()=>{}};"}));});
const org="11111111-1111-4111-8111-111111111111",foreign="22222222-2222-4222-8222-222222222222";
const origin="http://127.0.0.1:3100",headers={Origin:origin,"X-Organization-ID":org};
async function login(api:APIRequestContext,role="owner") {
  return api.post("/api/backend/api/v1/auth/login",{headers:{Origin:origin},data:{email:role+"@example.invalid",password:"fixture-password-only",captcha_token:"fixture-only"}});
}
async function uiLogin(page:Page,role="senior_developer") {
  await page.route("https://challenges.cloudflare.com/**",route=>route.fulfill({contentType:"application/javascript",body:"window.turnstile={render:(el,o)=>{el.textContent='Synthetic browser-test challenge';setTimeout(()=>o.callback('fixture-only'),0);return 'fixture';},remove:()=>{}};"}));
  await page.addInitScript(({org})=>{if(!localStorage.getItem("mesh-connected-organization"))localStorage.setItem("mesh-connected-organization",org);sessionStorage.setItem("mesh-preview-mode","connected");},{org});
  await page.goto("/login");await page.getByLabel("Email",{exact:true}).fill(role+"@example.invalid");await page.getByLabel("Password",{exact:true}).fill("fixture-password-only");await page.getByRole("button",{name:"Sign in to MESH",exact:true}).click();
  await expect(page).toHaveURL(role==="hr"?/\/people$/:role==="owner"?/\/owner$/:role==="security_analyst"?/\/vader$/:/\/devtrack$/,{timeout:20000});
  await expect(page.locator("#main")).toBeVisible();
}

test("proxy health and strict route allowlist",async({request})=>{
  const live=await request.get("/api/backend/health/live");expect(live.status()).toBe(200);expect(live.headers()["x-frame-options"]).toBe("DENY");
  expect((await request.get("/api/backend/api/v1/not-a-route")).status()).toBe(404);
  expect((await request.get("/api/backend/api/v1/users/me",{headers})).status()).toBe(401);
});
test("cross-site login and mutations fail before backend dispatch",async({request})=>{
  const response=await request.post("/api/backend/api/v1/auth/login",{headers:{Origin:"https://untrusted.invalid"},data:{email:"owner@example.invalid",password:"fixture-password-only",captcha_token:"fixture"}});
  expect(response.status()).toBe(403);expect((await request.storageState()).cookies).toHaveLength(0);
});
test("dedicated hosted-account helper cannot activate in the local test sandbox",async({request})=>{
  const info=await request.get("/api/preview-info");expect((await info.json()).dedicated_accounts_available).toBe(false);
  expect((await request.post("/api/preview-login",{headers:{Origin:origin},data:{role:"owner"}})).status()).toBe(503);
  expect((await request.post("/api/preview-login",{headers:{Origin:"https://untrusted.invalid"},data:{role:"owner"}})).status()).toBe(403);
});
test("session tokens are HttpOnly and never returned to JavaScript",async({request})=>{
  const response=await login(request);expect(response.status()).toBe(200);expect(await response.json()).toEqual({session_created:true,expires_in:3600});
  const cookies=(await request.storageState()).cookies;expect(cookies.length).toBeGreaterThan(0);for(const c of cookies){expect(c.httpOnly).toBe(true);expect(c.sameSite).toBe("Strict");}
  const user=await request.get("/api/backend/api/v1/users/me",{headers});expect(user.status()).toBe(200);expect((await user.json()).role).toBe("owner");
  expect((await request.get("/api/backend/api/v1/employees",{headers})).status()).toBe(403);
  expect((await request.get("/api/backend/api/v1/vader/incidents",{headers})).status()).toBe(403);
});
test("client role headers cannot grant finance or tenant access",async({request})=>{
  await login(request,"junior_developer");
  expect((await request.get("/api/backend/api/v1/finance/costs",{headers:{...headers,"X-Role":"owner"}})).status()).toBe(403);
  expect((await request.get("/api/backend/api/v1/users/me",{headers:{...headers,"X-Organization-ID":foreign}})).status()).toBe(403);
  expect((await request.get("/api/backend/api/v1/users/me",{headers:{...headers,"X-Organization-ID":"lumen"}})).status()).toBe(400);
});
test("larger provider tokens round-trip through HttpOnly chunks",async({request})=>{
  const response=await login(request,"chunked");expect(response.status()).toBe(200);
  const cookies=(await request.storageState()).cookies;expect(cookies.find(c=>c.name==="mesh_sandbox_access_count")?.value).toBe("3");
  const profile=await request.get("/api/backend/api/v1/users/me",{headers});expect(profile.status()).toBe(200);expect((await profile.json()).role).toBe("owner");
});
test("registration captures owner name in the real backend request contract",async({page})=>{
  await page.goto("/register");await page.getByLabel("Your full name",{exact:true}).fill("Preview Owner");await page.getByLabel("Email",{exact:true}).fill("new-fixture@example.invalid");await page.getByLabel("Password",{exact:true}).fill("fixture-password-only");
  const sent=page.waitForRequest(r=>r.url().endsWith("/api/backend/api/v1/auth/register")&&r.method()==="POST");
  await page.getByRole("button",{name:"Create your account",exact:true}).click();expect((await sent).postDataJSON().owner_name).toBe("Preview Owner");await expect(page.getByRole("status")).toContainText("Registration submitted");
});
test("refresh uses server cookie and logout removes it",async({request})=>{
  await login(request);expect((await request.post("/api/backend/api/v1/auth/refresh",{headers:{Origin:origin},data:{refresh_token:"ignored-browser-value"}})).status()).toBe(200);
  expect((await request.post("/api/backend/api/v1/auth/logout",{headers,data:{}})).status()).toBe(200);
  expect((await request.storageState()).cookies.filter(c=>c.name.startsWith("mesh_")).length).toBe(0);
  expect((await request.get("/api/backend/api/v1/users/me",{headers})).status()).toBe(401);
});
test("PDF and oversize images are rejected by the bridge",async({request})=>{
  await login(request,"hr");const path="/api/backend/api/v1/employees/bbbbbbbb-bbbb-4bbb-8bbb-000000000004/identity-documents";
  expect((await request.post(path,{headers:{...headers,"Content-Type":"application/pdf"},data:Buffer.from("fictional") })).status()).toBe(415);
  expect((await request.post(path,{headers:{...headers,"Content-Type":"image/png"},data:Buffer.alloc(2097153)})).status()).toBe(413);
});
test("native project proposal persists after reload without demo identities",async({page})=>{
  await uiLogin(page);await page.goto("/devtrack/projects");
  await page.getByRole("button",{name:/New project|Propose project|Propose a project|Submit a proposal|New proposal/}).first().click();
  const name="Native project "+Date.now();await page.getByLabel("Project name",{exact:true}).fill(name);await page.getByLabel("What will it achieve?",{exact:true}).fill("A real backend project created by the isolated browser test.");
  await expect(page.getByLabel("Budget (USD)",{exact:true})).toHaveCount(0);await page.getByRole("button",{name:"Submit proposal",exact:true}).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);await expect(page.getByText(name,{exact:true}).first()).toBeVisible();await page.reload();await expect(page.getByText(name,{exact:true}).first()).toBeVisible();
  await expect(page.getByText("Alex Morgan",{exact:true})).toHaveCount(0);await expect(page.getByLabel("Backend result")).toHaveCount(0);expect(await page.evaluate(()=>document.cookie)).not.toMatch(/mesh_(sandbox_)?(access|refresh)/);
  await page.screenshot({path:"connected-projects-desktop.png",fullPage:true});
});
test("invalid selected tenant shows an error and no previous records",async({page})=>{
  await uiLogin(page);await page.evaluate(foreign=>localStorage.setItem("mesh-connected-organization",foreign),foreign);await page.reload();
  await expect(page.getByRole("alert").filter({hasText:/membership|access|organization/i})).toBeVisible();await expect(page.locator("#main")).toHaveCount(0);await expect(page.getByRole("table")).toHaveCount(0);
});
test("native HR directory uses real employee names and fits mobile",async({page})=>{
  await page.setViewportSize({width:390,height:844});await uiLogin(page,"hr");await page.goto("/people/directory");await expect(page.getByRole("table")).toBeVisible();await expect(page.getByText("Fixture junior_developer",{exact:true}).first()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);await expect(page.getByText("Alex Morgan",{exact:true})).toHaveCount(0);await page.screenshot({path:"connected-employees-mobile.png",fullPage:true});
});
test("local sandbox uses backend role and security evidence screens",async({page})=>{
  await page.goto("/login");await page.getByLabel("Sandbox role",{exact:true}).selectOption("security_analyst");await page.getByRole("button",{name:"Open local sandbox",exact:true}).click();
  await expect(page).toHaveURL(/\/vader$/);await expect(page.getByRole("heading",{name:"VADER command center",exact:true})).toBeVisible();await expect(page.getByText("Local sandbox · fictional identities and test data.",{exact:true})).toBeVisible();await expect(page.getByText("Monitoring 214 assets",{exact:true})).toHaveCount(0);
});


test("native complaints persist and only independent HR can handle them",async({page,browser})=>{
  test.setTimeout(90000);
  await uiLogin(page,"junior_developer");await page.getByRole("link",{name:"My complaints",exact:true}).click();
  const subject="Isolated concern "+Date.now();
  await page.getByLabel("Subject",{exact:true}).fill(subject);await page.getByLabel("Your concern",{exact:true}).fill("Fictional concern for isolated workflow verification.");
  await page.getByRole("button",{name:"Submit concern",exact:true}).click();
  await expect(page.locator("#main").getByRole("status")).toHaveText("Concern saved for HR review.");
  await page.reload();await expect(page.getByRole("heading",{name:subject,exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Start investigation",exact:true})).toHaveCount(0);
  const own=await page.request.get("/api/backend/api/v1/hr/complaints",{headers});const id=(await own.json()).find((c:{subject:string})=>c.subject===subject).id;
  expect((await page.request.patch(`/api/backend/api/v1/hr/complaints/${id}`,{headers,data:{status:"investigating"}})).status()).toBe(403);
  const owner=await browser.newContext(),hr=await browser.newContext();
  try{
    const ownerPage=await owner.newPage();await uiLogin(ownerPage,"owner");await ownerPage.goto("/workspace/complaints");
    await expect(ownerPage.getByRole("heading",{name:"Your submitted concerns",exact:true})).toBeVisible();
    expect((await (await ownerPage.request.get("/api/backend/api/v1/hr/complaints",{headers})).json()).some((c:{id:string})=>c.id===id)).toBe(false);
    const reviewer=await hr.newPage();await uiLogin(reviewer,"hr");await reviewer.goto("/workspace/complaints");
    const row=reviewer.getByRole("listitem").filter({has:reviewer.getByRole("heading",{name:subject,exact:true})});
    await row.getByRole("button",{name:"Start investigation",exact:true}).click();await expect(row.getByRole("button",{name:"Resolve case",exact:true})).toBeVisible();
    await row.getByRole("button",{name:"Resolve case",exact:true}).click();await expect(row).toContainText("resolved");
    await reviewer.reload();await expect(reviewer.getByRole("listitem").filter({has:reviewer.getByRole("heading",{name:subject,exact:true})})).toContainText("resolved");
  }finally{await owner.close();await hr.close();}
});


test("native policy, synthetic scenario and risk assessment use backend state",async({page,browser})=>{
  test.setTimeout(90000);
  await uiLogin(page,"owner");await page.goto("/workspace/organization");
  await expect(page.getByRole("button",{name:"Create domain proof",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Create invitation",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Connect repository",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Create policy using backend defaults",exact:true}).click();
  await expect(page.getByText("Version 1 weights and thresholds",{exact:true})).toBeVisible();
  const context=await browser.newContext();
  try{
    const analyst=await context.newPage();await uiLogin(analyst,"security_analyst");await analyst.goto("/vader/simulation");
    await expect(analyst.getByRole("button",{name:"Run synthetic scenario",exact:true})).toBeDisabled();
    await analyst.getByRole("checkbox").check();await analyst.getByRole("button",{name:"Run synthetic scenario",exact:true}).click();
    await expect(analyst.getByText("3 synthetic events recorded.",{exact:true})).toBeVisible();
    await analyst.goto("/vader/risk");await analyst.getByRole("checkbox").check();await analyst.getByRole("button",{name:"Create assessment",exact:true}).click();
    await expect(analyst.getByRole("button",{name:"View assessment",exact:true}).first()).toBeVisible();
    await analyst.reload();await analyst.getByLabel("Assessment evidence source",{exact:true}).selectOption("synthetic");await analyst.getByRole("button",{name:"View assessment",exact:true}).first().click();
    await expect(analyst.getByText(/Coverage weight:/)).toBeVisible();await expect(analyst.getByText(/Missing evidence bounds:/)).toBeVisible();
    await analyst.goto("/workspace/settings");await expect(analyst.getByRole("button",{name:"Add authenticator",exact:true})).toBeVisible();
    expect((await analyst.request.post("/api/backend/api/v1/vader/risk-policies",{headers,data:{}})).status()).toBe(403);
  }finally{await context.close();}
});


test("foreign record IDs stay inaccessible despite a valid local session",async({playwright,request})=>{
 const foreignApi=await playwright.request.newContext({baseURL:origin});
 try{
  expect((await login(foreignApi,"foreign_senior")).ok()).toBe(true);
  const created=await foreignApi.post("/api/backend/api/v1/projects",{headers:{Origin:origin,"X-Organization-ID":foreign},data:{name:"Foreign private project",description:"Separate test tenant only"}});
  expect(created.status()).toBe(201);const id=(await created.json()).id;
  await login(request,"owner");
  const denied=await request.get(`/api/backend/api/v1/projects/${id}`,{headers});
  expect(denied.status()).toBe(404);expect(await denied.text()).not.toContain("Foreign private project");
 }finally{await foreignApi.dispose();}
});

test("native task status and priority persist after independent project approval",async({page,playwright})=>{
 const api=await playwright.request.newContext({baseURL:origin});
 try{
  await login(api,"junior_developer");
  const created=await api.post("/api/backend/api/v1/projects",{headers,data:{name:"Task integration "+Date.now(),description:"Independent review and task persistence"}});expect(created.status()).toBe(201);const project=(await created.json()).id;
  await login(api,"senior_developer");expect((await api.post(`/api/backend/api/v1/projects/${project}/reviews`,{headers,data:{comment:"Independent senior review"}})).ok()).toBe(true);
  await login(api,"owner");expect((await api.post(`/api/backend/api/v1/projects/${project}/decision`,{headers,data:{decision:"approved"}})).ok()).toBe(true);
  const member=await api.post(`/api/backend/api/v1/projects/${project}/members`,{headers,data:{user_id:"aaaaaaaa-aaaa-4aaa-8aaa-000000000004",manager:false}});expect([200,201,409]).toContain(member.status());
  expect((await api.post(`/api/backend/api/v1/projects/${project}/members`,{headers,data:{user_id:"aaaaaaaa-aaaa-4aaa-8aaa-000000000003",manager:true}})).status()).toBe(201);
  await login(api,"senior_developer");
  const title="Persisted task "+Date.now();const response=await api.post("/api/backend/api/v1/tasks",{headers,data:{project_id:project,assignee_id:"aaaaaaaa-aaaa-4aaa-8aaa-000000000004",title}});expect(response.status()).toBe(201);const id=(await response.json()).id;
  await uiLogin(page,"junior_developer");await page.goto("/devtrack/board");await page.getByRole("button",{name:new RegExp("Open .*"+title)}).click();
  const dialog=page.getByRole("dialog");await dialog.getByText("Status",{exact:true}).locator("..").getByRole("combobox").selectOption("In progress");
  await expect(dialog.getByRole("combobox").first()).toHaveValue("In progress");
  const saved=await page.request.get(`/api/backend/api/v1/projects/${project}/tasks`,{headers});expect(saved.ok()).toBe(true);expect((await saved.json()).find((task:{id:string})=>task.id===id).status).toBe("in_progress");
  await page.reload();await page.getByRole("button",{name:new RegExp("Open .*"+title)}).click();await expect(page.getByRole("dialog").getByRole("combobox").first()).toHaveValue("In progress");
  await login(page.request,"senior_developer");await page.reload();await page.getByRole("button",{name:new RegExp("Open .*"+title)}).click();
  await page.getByRole("dialog").getByRole("button",{name:"Edit task details",exact:true}).click();await page.getByLabel("Edit task priority").selectOption("High");await page.getByLabel("Edit task due date").fill("2026-11-15");await page.getByRole("dialog").getByRole("button",{name:/Save/}).click();await expect(page.getByRole("button",{name:"Edit task details",exact:true})).toBeVisible();const updated=await page.request.get(`/api/backend/api/v1/tasks/${id}/details`,{headers});expect(JSON.stringify(await updated.json())).toContain("high");
 }finally{await api.dispose();}
});

test("missing dates never render Invalid Date in connected project cards",async({page})=>{
 await uiLogin(page,"owner");await page.goto("/devtrack/projects");await expect(page.locator("#main")).not.toContainText("Invalid Date");await expect(page.locator("#main")).not.toContainText("$NaN");
});


test("native payroll rules calculate and persist an actual isolated payroll record",async({page})=>{
 await uiLogin(page,"hr");await page.goto("/people/payroll");const name="Payroll rule "+Date.now();
 await page.getByLabel("Rule name",{exact:true}).fill(name);await page.getByLabel("Rule version",{exact:true}).fill("1");await page.getByLabel("Rule currency",{exact:true}).fill("USD");
 await page.getByRole("button",{name:"Add component",exact:true}).click();await page.getByLabel("Component 1 name").fill("Tax fixture");await page.getByLabel("Component 1 formula").selectOption("percent_of_base");await page.getByLabel("Component 1 value").fill("10");
 const created=page.waitForResponse(r=>r.url().endsWith("/api/v1/hr/payroll-rules")&&r.request().method()==="POST");await page.getByRole("button",{name:"Save payroll rule",exact:true}).click();const response=await created;expect(response.status()).toBe(201);const id=(await response.json()).id;
 await page.getByLabel("Payroll employee",{exact:true}).selectOption("bbbbbbbb-bbbb-4bbb-8bbb-000000000004");await page.getByLabel("Payroll rule",{exact:true}).selectOption(id);await page.getByLabel("Base amount",{exact:true}).fill("1000");await page.getByLabel("Payroll period",{exact:true}).fill("2026-11");
 const computed=page.waitForResponse(r=>r.url().endsWith("/api/v1/hr/payroll/compute")&&r.request().method()==="POST");await page.getByRole("button",{name:"Compute and save record",exact:true}).click();const payroll=await computed;expect(payroll.status()).toBe(201);expect(Number((await payroll.json()).payroll.net)).toBe(900);
 await page.reload();const records=await page.request.get("/api/backend/api/v1/hr/payroll",{headers});expect((await records.json()).some((row:{net:string})=>Number(row.net)===900)).toBe(true);
});

test("all five roles can render their connected routes without browser exceptions",async({browser})=>{
 test.setTimeout(180000);
 const routes:Record<string,string[]>={owner:["/owner","/owner/projects","/owner/finance","/owner/performance","/workspace/organization","/workspace/audit","/workspace/settings","/workspace/insights","/devtrack/sprints"],hr:["/people","/people/directory","/people/administration","/people/payroll","/people/promotions","/people/leave/review","/people/verification"],senior_developer:["/devtrack","/devtrack/board","/devtrack/projects","/devtrack/security","/workspace/insights"],junior_developer:["/devtrack","/workspace/leave","/workspace/complaints","/workspace/settings","/workspace/trust"],security_analyst:["/vader","/vader/incidents","/vader/behavior","/vader/cloud","/vader/attack-chain","/vader/risk","/vader/simulation","/vader/copilot"]};
 for(const [role,paths]of Object.entries(routes)){const context=await browser.newContext();try{const page=await context.newPage(),errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));await uiLogin(page,role);for(const path of paths){await page.goto(path);await expect(page.locator("#main")).toBeVisible();await expect(page.locator("body")).not.toContainText("Application error:");await expect(page.locator("#main")).not.toContainText("Invalid Date");}expect(errors).toEqual([]);}finally{await context.close();}}
});


test("authenticator step-up loads without an organization profile",async({page})=>{
 await login(page.request,"owner");const sent=page.waitForRequest(r=>r.url().endsWith("/api/backend/api/v1/auth/mfa/factors"));await page.goto("/mfa");await expect(page.getByRole("heading",{name:"Verify your account",exact:true})).toBeVisible();expect((await sent).headers()["x-organization-id"]).toBeUndefined();await expect(page.getByRole("link",{name:"Continue to workspace",exact:true})).toBeVisible();
});


test("reviewed Trust events are saved and reflected in the backend score",async({page})=>{
 await uiLogin(page,"owner");await page.goto("/workspace/trust");await page.getByLabel("Reviewed account reference",{exact:true}).fill("aaaaaaaa-aaaa-4aaa-8aaa-000000000004");await page.getByLabel("Evidence reference",{exact:true}).fill("fictional-review-"+Date.now());await page.getByLabel("Reviewed score change",{exact:true}).fill("2");await page.getByLabel("Reviewed reason",{exact:true}).fill("Fictional evidence reviewed for isolated browser acceptance.");await page.getByLabel("I reviewed the supporting evidence.",{exact:true}).check();const saved=page.waitForResponse(r=>r.url().endsWith("/api/v1/trust/events")&&r.request().method()==="POST");await page.getByRole("button",{name:"Record reviewed event",exact:true}).click();expect((await saved).status()).toBe(201);await page.getByLabel("Employee user reference",{exact:true}).fill("aaaaaaaa-aaaa-4aaa-8aaa-000000000004");await page.getByRole("button",{name:"Load reviewed score",exact:true}).click();await expect(page.getByText(/22 \/ 50/)).toBeVisible();
});
