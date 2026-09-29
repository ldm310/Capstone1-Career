import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";

test("home destinations are readable, accessible and responsive", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/#features");
  const destinations = [
    "/jobs",
    "/my-skills",
    "/preparation",
    "/application-tracker",
    "/growth",
  ];
  for (const [index, href] of destinations.entries())
    await expect(page.locator(".home-feature-card").nth(index)).toHaveAttribute(
      "href",
      href,
    );
  for (const width of [1440, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    for (const card of await page.locator(".home-feature-card").all()) {
      expect(
        await card.evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page
    .getByRole("navigation", { name: "주 메뉴" })
    .getByRole("link", { name: "채용공고", exact: true })
    .click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.getByRole("button", { name: "메뉴 열기" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
});

test("clouds share a 5 second clock across intro and home and support pause", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.clock.install();
  await page.goto("/");
  // Wait for every local photo to be decoded before controlling time.
  await page.evaluate(async () => {
    await Promise.all(
      [
        "/images/career-sky.jpg",
        "/images/career-clouds-2.jpg",
        "/images/career-clouds-3.jpg",
      ].map(
        (src) =>
          new Promise<void>((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve();
            img.onerror = reject;
            img.src = src;
          }),
      ),
    );
  });
  const intro = page.locator(".intro-sky-photo");
  const home = page.locator(".home-sky-photo");
  const before = await intro.getAttribute("data-cloud-index");
  await page.clock.runFor(5100);
  await expect(intro).not.toHaveAttribute("data-cloud-index", before!);
  await expect(home).toHaveAttribute(
    "data-cloud-index",
    (await intro.getAttribute("data-cloud-index"))!,
  );
  await page
    .getByRole("button", { name: "구름 배경 자동 전환 일시정지" })
    .click();
  const paused = await intro.getAttribute("data-cloud-index");
  await page.clock.runFor(11000);
  await expect(intro).toHaveAttribute("data-cloud-index", paused!);
  await page.getByRole("button", { name: "Career 홈페이지 열기" }).click();
  await page.clock.runFor(1000);
  await expect(home).toHaveAttribute("data-cloud-index", paused!);
  await page.getByRole("button", { name: "구름 배경 자동 전환 재생" }).click();
  await page.clock.runFor(4000);
  await expect(home).toHaveAttribute("data-cloud-index", paused!);
  await page.clock.runFor(1100);
  await expect(home).not.toHaveAttribute("data-cloud-index", paused!);
});

test("reduced motion starts paused and failed cloud images keep original fallback", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.route("**/images/career-clouds-*.jpg", (route) => route.abort());
  await page.goto("/");
  await expect(page.locator(".intro-sky-photo")).toHaveAttribute(
    "data-paused",
    "true",
  );
  await page.getByRole("button", { name: "구름 배경 자동 전환 재생" }).click();
  await page.clock.install();
  await page.clock.runFor(15000);
  await expect(page.locator(".intro-sky-photo")).toHaveAttribute(
    "data-cloud-index",
    "0",
  );
});
