import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 3120);

export default defineConfig({
  testDir: "./e2e",
  globalTeardown: "./scripts/browser-teardown.ts",
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "e2e/.results.json" }]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, channel: "chrome", trace: "retain-on-failure", contextOptions: { reducedMotion: "reduce" } },
  // Tests run against the production build: `npm run build` first.
  webServer: { command: `"${process.execPath}" scripts/test-frontend.mjs`, url: `http://127.0.0.1:${PORT}/login`, reuseExistingServer: false, timeout: 60_000 },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
});
