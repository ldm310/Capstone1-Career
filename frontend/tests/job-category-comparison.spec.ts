import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const detail = "/jobs?job=study-demo-backend&demo=low";

test("failed benchmark requests remain an error and can retry", async ({
  page,
}) => {
  let fail = true;
  await page.route("**/api/jobs/benchmark?**", (route) =>
    fail
      ? route.fulfill({ status: 502, json: { error: "Unavailable" } })
      : route.continue(),
  );
  await page.goto(detail);
  await expect(page.locator(".comparison-message[role=alert]")).toContainText(
    "비교 자료를 불러오지 못했어요.",
  );
  await expect(page.locator(".category-radar")).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.locator(".category-radar")).toHaveCount(2);
});

test("three detail states show the right charts and no lower stats table", async ({
  page,
}) => {
  await page.goto(detail);
  const tabs = page.getByRole("navigation", { name: "공고 상세 메뉴" });
  await expect(tabs.getByRole("link")).toHaveText(["스탯 분석", "지원 조건"]);
  await expect(page.locator(".comparison-radar-card")).toHaveCount(2);
  await expect(page.getByText("가상 합격자 50명 기준")).toBeVisible();
  await expect(
    page.locator(".category-radar").first().locator("g"),
  ).toHaveCount(10);
  await expect(
    page.locator(".applicant-stats, .passed-preferred, [role=progressbar]"),
  ).toHaveCount(0);
  await page.screenshot({
    path: "work/comparison-with-passers.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "합격자 없음", exact: true }).click();
  await expect(
    page.getByText("합격자 데이터가 아직 없어요.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".comparison-radar-card")).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "합격자 vs 나 스탯", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "work/comparison-no-passers.png",
    fullPage: true,
  });
  await tabs.getByRole("link", { name: "지원 조건", exact: true }).click();
  await expect(page.locator(".application-condition-rows")).toContainText(
    "3.8",
  );
  await expect(page.locator(".application-condition-rows")).toContainText(
    "2개",
  );
  await expect(page.locator(".category-radar")).toHaveCount(0);
  await page.screenshot({
    path: "work/comparison-conditions.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "공고 정보 확인" }).click();
  await expect(page.locator(".job-original-panel")).toHaveAttribute("open", "");
  await expect(page.locator(".job-posting-section").first()).toBeVisible();
});

test("mobile states fit and remain accessible", async ({ page }) => {
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(detail);
    await expect(page.locator(".category-radar")).toHaveCount(2);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("link", { name: "지원 조건", exact: true }).click();
    await expect(page.locator(".application-conditions")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({ path: "work/comparison-mobile.png", fullPage: true });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.goto(detail);
  await expect(page.locator(".category-radar")).toHaveCount(2);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});
