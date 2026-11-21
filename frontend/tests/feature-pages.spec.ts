import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";

test("each header menu opens its independent section", async ({ page }) => {
  await mockPublicJobs(page);
  const sections = [
    ["채용공고", "/jobs", "채용공고", []],
    ["분석", "/analysis", "분석", []],
  ] as const;
  for (const [action, url, title, tabs] of sections) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/#market-preview");
    await page
      .getByRole("navigation", { name: "주 메뉴" })
      .getByRole("link", { name: action, exact: true })
      .click();
    await expect(page).toHaveURL(new RegExp(url + "$"));
    await expect(
      page.getByRole("heading", { level: 1, name: title, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".sidebar")).toHaveCount(0);
    // 하위 메뉴가 하나뿐인 화면은 탭을 숨긴다.
    if (tabs.length)
      await expect(
        page
          .getByRole("navigation", { name: title + " 하위 메뉴" })
          .getByRole("link"),
      ).toHaveText([...tabs]);
    else
      await expect(
        page.getByRole("navigation", { name: title + " 하위 메뉴" }),
      ).toHaveCount(0);
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 960 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${url} width ${width}`,
      ).toBe(true);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    const a = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(a.violations, url).toEqual([]);
  }
});

test("catalog filters and comparison URL stay inside jobs", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/jobs");
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await page.locator("summary").filter({ hasText: "상세조건" }).click();
  await page.getByLabel("지역 검색").fill("부산");
  await expect(page.locator(".public-job-card")).toHaveCount(0);
  await page.getByRole("button", { name: "필터 초기화" }).click();
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await page.route("**/api/analyze", (route) =>
    route.fulfill({
      json: {
        workspace: {
          runs: [],
          job: {
            id: "a",
            company: "매치그룹",
            title: "Backend Engineer 1",
            url: "https://jobs.lever.co/zoyi/fixture-0",
            required: ["SQL"],
            preferred: ["Docker"],
            unknown: [],
            text: "자격요건\nSQL",
          },
        },
      },
    }),
  );
  await page
    .locator(".public-job-card")
    .filter({
      has: page.getByRole("heading", {
        name: "Backend Engineer 1",
        exact: true,
      }),
    })
    .getByRole("link", { name: "스탯 분석 →" })
    .click();
  await expect(page).toHaveURL(/\/jobs\?job=fixture-0&view=stats$/);
  await expect(
    page.getByRole("navigation", { name: "공고 상세 메뉴" }).getByRole("link"),
  ).toHaveText(["스탯 분석", "지원 조건"]);
  await expect(page.getByLabel("지원 자격 점수 산정 전")).toBeVisible();
});

test("old links preserve destination and removed sections are gone", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/career?tab=plan");
  await expect(page).toHaveURL(/\/jobs$/);
  await page.goto("/career?tab=sources");
  await expect(page).toHaveURL(/\/analysis$/);
  await page.goto("/my-skills?tab=schedule");
  await expect(page).toHaveURL(/\/jobs$/);
  for (const url of [
    "/studies",
    "/application-tracker",
    "/growth",
    "/preparation",
    "/dashboard",
    "/applications",
  ]) {
    const response = await page.goto(url);
    expect(response?.status(), url).toBe(404);
  }
});

test("catalog loads more than one page and filters send complete query to API", async ({
  page,
}) => {
  const rows = Array.from({ length: 17 }, (_, i) => ({
    id: `more-${i}`,
    company: "검증 회사",
    title: `AI 개발자 ${i + 1}`,
    category: "backend",
    location: "서울",
    employment: "정규직",
    workplace: "하이브리드 근무",
    postedAt: "2026-09-29T00:00:00Z",
    url: `https://jobs.lever.co/zoyi/more-${i}`,
    skills: ["Python"],
  }));
  await page.route("**/api/jobs?**", async (route) => {
    const p = new URL(route.request().url()).searchParams;
    const offset = Number(p.get("offset")),
      limit = Number(p.get("limit"));
    await route.fulfill({
      json: {
        jobs: rows.slice(offset, offset + limit),
        total: rows.length,
        nextOffset: offset + limit < rows.length ? offset + limit : null,
        checkedAt: new Date().toISOString(),
        unavailableSources: [],
      },
    });
  });
  await page.goto("/jobs");
  await expect(page.locator(".public-job-card")).toHaveCount(12);
  await page.getByRole("button", { name: "더보기", exact: true }).click();
  await expect(page.locator(".public-job-card")).toHaveCount(17);
  const request = page.waitForRequest(
    (r) =>
      r.url().includes("/api/jobs?") &&
      new URL(r.url()).searchParams.get("q") === "Python",
  );
  await page.getByLabel("전체 연동 공고 검색").fill("Python");
  await request;
  await expect(page.locator(".public-job-card")).toHaveCount(12);
});
