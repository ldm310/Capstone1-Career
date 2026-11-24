import { defineConfig } from "@playwright/test";

// Server-side contracts use local HTTP stubs and an isolated local PostgreSQL DB.
export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "backend-jobs.spec.ts",
    "backend-api-contract.spec.ts",
    "hiring-cohort.spec.ts",
    "extraction-review-storage.spec.ts",
    "job-catalog-storage.spec.ts",
    "posting-metadata.spec.ts",
  ],
  workers: 1,
  reporter: "list",
  outputDir: "work/api-contract-results",
});
