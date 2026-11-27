import { test, expect } from "@playwright/test";
import { fixtureJobs } from "./public-jobs-fixture";

test("job pages show totals, replace rows, reset filters and handle no results", async ({
  page,
}) => {
  await page.route("**/api/jobs?**", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get("offset"));
    const total = params.get("q") ? 0 : params.get("role") === "data" ? 1 : 27;
    const jobs = Array.from({ length: total }, (_, index) => ({
      ...fixtureJobs[0],
      id: `page-${index}`,
      title: `Backend Engineer ${index + 1}`,
      category: total === 1 ? "data" : "backend",
    }));
    await route.fulfill({
      json: {
        jobs: jobs.slice(offset, offset + 12),
        total,
        nextOffset: offset + 12 < total ? offset + 12 : null,
        checkedAt: new Date().toISOString(),
        unavailableSources: [],
      },
    });
  });
  await page.goto("/jobs");
  const navigation = page.getByRole("navigation", { name: "채용 공고 페이지" });
  await expect(navigation).toContainText("총 27개, 1–12개 표시");
  await expect(navigation).toContainText("1 / 3 페이지");
  await expect(
    navigation.getByRole("button", { name: "이전", exact: true }),
  ).toBeDisabled();
  await navigation.getByRole("button", { name: "3페이지로 이동" }).click();
  await expect(navigation).toContainText("3 / 3 페이지");
  await expect(navigation).toContainText("25–27개 표시");
  await expect(page.locator(".job-list-row")).toHaveCount(3);
  await expect(
    navigation.getByRole("button", { name: "다음", exact: true }),
  ).toBeDisabled();
  await navigation.getByRole("button", { name: "이전", exact: true }).click();
  await expect(navigation).toContainText("2 / 3 페이지");
  await expect(page.locator(".job-list-row")).toHaveCount(12);
  await page.getByLabel("공고 직무", { exact: true }).selectOption("data");
  await expect(navigation).toContainText("총 1개, 1–1개 표시");
  await expect(navigation).toContainText("1 / 1 페이지");
  await page.getByLabel("전체 연동 공고 검색").fill("없는공고");
  await expect(navigation).toContainText("총 0개");
  await expect(navigation.locator("button")).toHaveCount(0);
  await expect(page.locator(".public-job-empty")).toContainText(
    "조건에 맞는 공고",
  );
});

test("notice pages retain the page after reading and fit mobile", async ({
  page,
}) => {
  await page.route("**/api/notices?**", async (route) => {
    const offset = Number(
      new URL(route.request().url()).searchParams.get("offset"),
    );
    const notices = Array.from({ length: 23 }, (_, index) => ({
      id: `notice-${index}`,
      title: `공지 ${index + 1}`,
      content: "서비스 이용 안내",
      authorName: "관리자",
      pinned: false,
      createdAt: "2026-11-24T00:00:00Z",
      updatedAt: "2026-11-24T00:00:00Z",
    }));
    await route.fulfill({
      json: {
        notices: notices.slice(offset, offset + 20),
        total: 23,
        nextOffset: offset === 0 ? 20 : null,
        canManage: false,
      },
    });
  });
  await page.goto("/notices");
  const navigation = page.getByRole("navigation", { name: "공지사항 페이지" });
  await expect(navigation).toContainText("1 / 2 페이지");
  await expect(page.locator(".notice-list > li")).toHaveCount(20);
  await navigation.getByRole("button", { name: "다음", exact: true }).click();
  await expect(navigation).toContainText("총 23개, 21–23개 표시");
  await expect(page.locator(".notice-list > li")).toHaveCount(3);
  await page.locator(".notice-list > li").first().getByRole("button").click();
  await page.getByRole("button", { name: "공지 목록", exact: true }).click();
  await expect(navigation).toContainText("2 / 2 페이지");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    navigation.getByRole("button", { name: "다음", exact: true }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await navigation.getByRole("button", { name: "이전", exact: true }).click();
  await expect(navigation).toContainText("1 / 2 페이지");
});
