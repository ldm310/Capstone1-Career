import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";
test("sky intro enters with keyboard, restores focus, remembers and replays", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/");
  const enter = page.getByRole("button", { name: "Career 홈페이지 열기" });
  await expect(enter).toBeFocused();
  await enter.press("Tab");
  await expect(
    page.getByRole("button", { name: "구름 배경 자동 전환 재생", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(enter).toBeFocused();
  await expect(page.locator(".intro-click-link")).toHaveCSS(
    "outline-style",
    "none",
  );
  await expect(page.locator(".intro-click-link")).toHaveCSS(
    "box-shadow",
    "rgb(39, 79, 111) 0px 1px 0px 0px",
  );
  await expect(page.locator(".sky-home")).toHaveAttribute("inert", "");
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  await enter.press("Enter");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".sky-hero h1")).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  await page.reload();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "인트로 다시 보기" }).click();
  await expect(enter).toBeFocused();
  await enter.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("link", { name: "내 역량 확인하기", exact: true })
    .click();
  await expect(page).toHaveURL(/my-skills/);
});
test("mouse parallax, animated reveal and mobile tap", async ({ page }) => {
  await mockPublicJobs(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  await page.mouse.move(1100, 240);
  await expect
    .poll(() =>
      page
        .locator(".intro-title-group")
        .evaluate((el) => getComputedStyle(el).transform),
    )
    .not.toBe("none");
  await page.getByRole("button", { name: "Career 홈페이지 열기" }).click();
  await expect(page.locator(".sky-experience")).toHaveClass(
    /sky-phase-leaving/,
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.setViewportSize({ width: 320, height: 740 });
  await page.getByRole("button", { name: "인트로 다시 보기" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Career 홈페이지 열기" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("in-page links skip the intro", async ({ page }) => {
  await mockPublicJobs(page);
  await page.goto("/#market-preview");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".public-job-card")).toHaveCount(3);
});
