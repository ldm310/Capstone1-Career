import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "auth-security.spec.ts",
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: "http://127.0.0.1:3108",
    channel: process.env.PLAYWRIGHT_CHANNEL,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  outputDir: "work/auth-test-results",
  reporter: "list",
  webServer: {
    command: "node tests/fixtures/auth-server.cjs",
    url: "http://127.0.0.1:3108/api/auth/kakao/status",
    reuseExistingServer: false,
    timeout: 120000,
  },
});
