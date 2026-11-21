import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";

test("job rows retain existing fields without placeholder logos or reference-only data", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/jobs");
  const rows = page.locator(".job-list-row");
  await expect(rows).toHaveCount(7);
  const first = rows.first();
  for (const text of [
    "매치그룹",
    "Backend Engineer 1",
    "백엔드",
    "서울",
    "정규직",
    "하이브리드 근무",
    "공고의 역량 키워드와 내 경험을 비교해요",
    "마감일 원문 확인",
  ])
    await expect(first).toContainText(text);
  await expect(
    page.locator(".public-company-mark, .home-job-mark, .job-company-logo"),
  ).toHaveCount(0);
  await expect(first).not.toContainText(
    /TOP100|대기업|외국계|학력무관|접수예정|홈페이지 지원/,
  );
  const firstBox = (await first.boundingBox())!;
  const secondBox = (await rows.nth(1).boundingBox())!;
  expect(secondBox.y).toBeGreaterThanOrEqual(firstBox.y + firstBox.height - 1);
  expect(secondBox.x).toBe(firstBox.x);
  const company = (await first.locator(".job-list-company").boundingBox())!;
  const title = (await first.locator("h3").boundingBox())!;
  const meta = (await first.locator(".job-list-meta").boundingBox())!;
  expect(company.x).toBeLessThan(title.x);
  expect(title.x).toBeLessThan(meta.x);
  await page.screenshot({ path: "work/job-list-desktop.png", fullPage: true });
  await first
    .getByRole("button", { name: "Backend Engineer 1 저장", exact: true })
    .click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(
    first.getByRole("button", {
      name: "Backend Engineer 1 저장 취소",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await first.getByRole("link", { name: "스탯 분석 →", exact: true }).click();
  await expect(page).toHaveURL(/job=fixture-0&view=stats/);
});

test("rows fit mobile widths, examples use the same list, and existing filters work", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/jobs");
  await expect(page.locator(".job-list-row")).toHaveCount(7);
  for (const width of [768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  }
  await page.screenshot({ path: "work/job-list-mobile.png", fullPage: true });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByLabel("공고 직무").selectOption("data");
  await expect(page.locator(".job-list-row")).toHaveCount(1);
  await expect(page.locator(".job-list-row h3")).toHaveText("Data Engineer 7");
  await page.goto("/jobs?demo=low");
  await expect(page.locator(".job-list-row")).toHaveCount(3);
  await expect(page.locator(".qualification-summary")).toHaveCount(3);
  await expect(page.locator(".public-company-mark")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
