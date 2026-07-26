import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"]],
  outputDir: join(tmpdir(), "cortex-bridge-playwright", "artifacts"),
  use: {
    baseURL: "http://127.0.0.1:3420",
    browserName: "chromium",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3420",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
