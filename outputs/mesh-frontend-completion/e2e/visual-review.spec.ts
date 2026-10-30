import { test, expect } from "@playwright/test";
import { asRole, type RoleId } from "./helpers";
const modules: [string,RoleId][] = [["/owner","owner"],["/people","hr"],["/devtrack/board","senior-dev"],["/vader","security-analyst"]];
for(const [route,role] of modules) for(const width of [390,768,1440]) {
 test(`visual review ${route} at ${width}`,async({page})=>{
  await page.setViewportSize({width,height:950});await asRole(page,role);
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(route);await expect(page.locator("main h1")).toBeVisible();
  await page.waitForTimeout(700);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  if(route === "/vader") {
    const label=page.locator(".recharts-polar-angle-axis-tick-value").filter({hasText:/cloud posture/i}).first();
    const bounds=await label.boundingBox();
    const svg=await label.locator("xpath=ancestor::*[local-name()='svg']").boundingBox();
    expect(bounds).not.toBeNull();expect(svg).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(svg!.x-1);
    expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(svg!.x+svg!.width+1);
  }
  await page.screenshot({path:`test-results/module-${role}-${width}.png`,fullPage:true});
  expect(errors).toEqual([]);
 });
}
