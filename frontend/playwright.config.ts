import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    channel: process.env.PLAYWRIGHT_CHANNEL,
    baseURL: "http://127.0.0.1:3000",
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  outputDir: "work/test-results",
  reporter: "list",
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    // 스테이징 LV 서비스(분석 칸·API)는 스테이징 스위치가 켜진 서버에서만 돈다(lv-stat/service/CONTRACT.md).
    env: { CAREER_LV_STAT: "on" },
  },
});
