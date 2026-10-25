import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
// Playwright's generated AI error context includes literal password field values.
// Keep credentials out of those snapshots, including when a login test fails.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
if (existsSync("../.env")) process.loadEnvFile("../.env");
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: process.env.E2E_LIVE_MODEL === "true" ? 180_000 : 60_000,
  expect: { timeout: process.env.E2E_LIVE_MODEL === "true" ? 90_000 : 10_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    actionTimeout: 10000,
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
