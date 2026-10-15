import type { Page } from "@playwright/test";
import type { PublicJob } from "../types/public-job";
export const fixtureJobs: PublicJob[] = Array.from({ length: 7 }, (_, i) => ({
  id: `fixture-${i}`,
  company: i % 2 ? "채널코퍼레이션" : "매치그룹",
  title: `${i === 6 ? "Data" : "Backend"} Engineer ${i + 1}`,
  category: i === 6 ? "data" : "backend",
  location: "서울",
  employment: "정규직",
  workplace: "하이브리드 근무",
  postedAt: `2026-09-${25 - i}T00:00:00.000Z`,
  url: `https://jobs.lever.co/zoyi/fixture-${i}`,
}));
export async function mockPublicJobs(page: Page) {
  await page.route("**/api/jobs?**", async (route) => {
    const p = new URL(route.request().url()).searchParams;
    const offset = Number(p.get("offset")),
      limit = Number(p.get("limit")),
      role = p.get("role");
    const jobs = fixtureJobs.filter(
      (job) => role === "all" || job.category === role,
    );
    await route.fulfill({
      json: {
        jobs: jobs.slice(offset, offset + limit),
        total: jobs.length,
        nextOffset: offset + limit < jobs.length ? offset + limit : null,
        checkedAt: "2026-09-25T10:00:00.000Z",
        unavailableSources: [],
      },
    });
  });
}
