import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("public capability experience uses one current posting, separate panels and LV tooltips without private analysis", async ({
  page,
}) => {
  await page.route("**/api/account", (route) =>
    route.fulfill({ json: { user: null, guest: false } }),
  );
  const mutations: string[] = [],
    privateRequests: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") mutations.push(request.url());
    if (
      /\/api\/(career|growth|jobs\/my-levels|analysis-preview|analyze)(\?|$)/.test(
        request.url(),
      )
    )
      privateRequests.push(request.url());
  });
  await page.goto("/#market-preview");
  await page.getByRole("link", { name: "역량 체험하기", exact: true }).click();
  await expect(page).toHaveURL(/\/experience$/);
  await expect(
    page.getByRole("heading", { name: "백엔드 서비스 개발자", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("tab", { name: "역량 분석", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  const chart = page.getByTestId("saved-level-radar");
  await expect(chart).toBeVisible();
  await expect(
    page.locator(
      ".example-switcher, .personal-keyword-list, .qualification-summary, .skill-row, .job-posting-section",
    ),
  ).toHaveCount(0);
  const mine = chart.locator(
    '.radar-point[aria-label="데이터베이스: 내 LV 94"]',
  );
  await mine.hover();
  await expect(mine.getByRole("tooltip")).toContainText("내 LV 94");
  await page.getByRole("tab", { name: "공고 내용", exact: true }).click();
  await expect(page).toHaveURL(/\/experience\?view=posting$/);
  await expect(page.locator(".job-posting-section")).toHaveCount(3);
  await expect(chart).toHaveCount(0);
  await expect(page.locator(".job-posting")).toContainText(
    "Backend 개발 경력 3년 이상",
  );
  await page.getByRole("tab", { name: "역량 분석", exact: true }).click();
  await expect(chart).toBeVisible();
  await page.mouse.move(0, 0);
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 950 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(mutations).toEqual([]);
  expect(privateRequests).toEqual([]);
  await page.screenshot({
    path: "work/current-posting-experience.png",
    fullPage: true,
  });
});
test("old onboarding URL opens the same posting experience", async ({
  page,
}) => {
  await page.goto("/onboarding");
  await expect(page).toHaveURL(/\/experience$/);
  await expect(page.getByTestId("saved-level-radar")).toBeVisible();
});
