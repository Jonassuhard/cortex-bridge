import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: "http://127.0.0.1:3420",
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: {
    command: "python3 -m http.server 3420 --bind 127.0.0.1 --directory out",
    url: "http://127.0.0.1:3420",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
