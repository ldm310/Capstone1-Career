import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";

test.beforeEach(async ({ page }) => {
  await mockPublicJobs(page);
  await page.route("**/api/account", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "layout-member",
          name: "검토 회원",
          email: "layout-review@example.com",
        },
        guest: false,
        profile: {},
      },
    }),
  );
  await page.route("**/api/saved-jobs", (route) =>
    route.fulfill({ json: { jobs: [] } }),
  );
});

test("home entry cards have no icons and keep space between headings, text and links", async ({
  page,
}) => {
  await page.goto("/#market-preview");
  const cards = page.locator(".home-panel");
  await expect(cards).toHaveCount(2);
  await expect(cards.locator("svg")).toHaveCount(0);
  await expect(cards.locator("h2")).toHaveText(["자료 분석", "채용공고"]);
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const card of await cards.all()) {
      const title = (await card.locator("h2").boundingBox())!;
      const text = (await card.locator(":scope > p").boundingBox())!;
      const link = (await card.locator(".home-panel-action").boundingBox())!;
      expect(text.y - title.y - title.height).toBeGreaterThanOrEqual(18);
      expect(link.y - text.y - text.height).toBeGreaterThanOrEqual(26);
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("primary screens keep a visible heading gap and fit desktop, tablet and small mobile", async ({
  page,
}) => {
  const screens = [
    ["home", "/#market-preview", ".home-panel"],
    ["analysis", "/analysis", "#analysis-start-title"],
    ["jobs", "/jobs", ".job-list-row"],
    ["detail", "/jobs?job=study-demo-backend&demo=low", ".job-public-content"],
    [
      "conditions",
      "/jobs?job=study-demo-backend-intern&demo=low",
      ".personal-job-comparison",
    ],
    ["sign-in", "/sign-in", ".sign-in-panel"],
    ["profile", "/my-page?tab=profile", ".mypage-form"],
    ["saved", "/my-page", ".mypage-empty"],
  ] as const;
  for (const [name, url, ready] of screens) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(url);
    await expect(page.locator(ready).first()).toBeVisible();
    if (name === "home")
      await expect(page.locator(".job-list-row")).toHaveCount(3);
    const heading = page.locator(".feature-page-heading");
    if (await heading.count()) {
      const headingBox = (await heading.boundingBox())!;
      const bodyBox = (await page.locator(".feature-body").boundingBox())!;
      expect(
        bodyBox.y - headingBox.y - headingBox.height,
        name,
      ).toBeGreaterThanOrEqual(28);
    }
    await page.screenshot({
      path: `work/ui-review/${name}-desktop.png`,
      fullPage: true,
    });
    for (const width of [768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${name} at ${width}px`,
      ).toBe(true);
    }
    await page.screenshot({
      path: `work/ui-review/${name}-mobile.png`,
      fullPage: true,
    });
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
      name,
    ).toEqual([]);
  }
});
