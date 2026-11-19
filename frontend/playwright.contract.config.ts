import { defineConfig } from "@playwright/test";

// Server-side API contracts use a local HTTP stub; no browser or external service.
export default defineConfig({
  testDir: "./tests",
  testMatch: ["backend-jobs.spec.ts", "backend-api-contract.spec.ts"],
  workers: 1,
  reporter: "list",
  outputDir: "work/api-contract-results",
});
