import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
if (existsSync("../.env")) process.loadEnvFile("../.env");
export default defineConfig({
  testDir: "./tests/smoke",
  workers: 1,
  retries: 0,
  timeout: 30000,
  reporter: "list",
  outputDir: "test-results/smoke",
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:8080",
    actionTimeout: 10000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
