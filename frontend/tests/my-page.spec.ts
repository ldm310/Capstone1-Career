import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("career:sky-intro:seen", "yes"),
  );
});

test("demo account sees saved jobs and its profile on my page", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "데모 계정으로 로그인" }).click();
  await expect(page).toHaveURL(/\/my-skills$/);
  await page.locator(".header-user").click();
  await expect(page).toHaveURL(/\/my-page$/);
  await expect(page.locator(".mypage-jobs li").first()).toBeVisible();
  // Demo data exists, so saved cards compare the passed average with my LV.
  await expect(page.locator(".mypage-jobs .passed-gap").first()).toContainText(
    /합격자 평균 LV \d+, 나 LV \d+/,
  );
  const before = await page.locator(".mypage-jobs li").count();
  expect(before).toBeGreaterThanOrEqual(1);
  await page.goto("/my-page?tab=profile");
  await expect(page.locator(".mypage-summary")).toContainText("김커리어");
  await expect(page.getByLabel("이메일")).toBeDisabled();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  const a = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(a.violations).toEqual([]);
});

test("job detail shows a visual summary and saves to my page", async ({
  page,
}) => {
  await page.goto("/jobs?job=dummy%3Acommerce-backend");
  const summary = page.locator(".job-summary");
  await expect(summary.locator("h2")).toHaveText(
    "커머스 백엔드 개발자 (경력 3년 이상)",
  );
  await expect(summary).toContainText("대졸(4년제) 이상");
  await expect(page.locator(".job-countdown")).toBeVisible();
  await expect(page.locator(".job-company")).toContainText("중견기업");
  await page.getByRole("button", { name: "공고 저장" }).click();
  await expect(
    page.getByRole("button", { name: "공고 저장 취소" }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.goto("/my-page");
  await expect(page.locator(".mypage-jobs h3")).toHaveText(
    "커머스 백엔드 개발자 (경력 3년 이상)",
  );
  await page.locator(".mypage-jobs li").click({ position: { x: 400, y: 20 } });
  await expect(page).toHaveURL(/job=dummy%3Acommerce-backend/);
  await page.goto("/my-page");
  await page.getByRole("button", { name: /저장 취소$/ }).click();
  await expect(page.getByText("저장한 공고가 없어요.")).toBeVisible();
});

test("a signed-in user edits profile and password", async ({
  page,
  baseURL,
}) => {
  const email = `me-${Date.now()}@career.test`;
  const r = await page.request.post("/api/account", {
    headers: { Origin: baseURL! },
    data: {
      action: "register",
      email,
      password: "first-password-1",
      name: "처음이름",
    },
  });
  expect(r.ok()).toBe(true);
  await page.goto("/my-page?tab=profile");
  await page.getByLabel("이름").fill("바뀐이름");
  await page.getByLabel("최종 학력").selectOption("대졸(4년제)");
  await page.getByLabel("희망 근무지").fill("부산");
  await page.getByLabel("GitHub").fill("not a url");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  expect(
    await page
      .getByLabel("GitHub")
      .evaluate((el) => (el as HTMLInputElement).validity.valid),
  ).toBe(false);
  await page.getByLabel("GitHub").fill("https://github.com/me");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("저장했어요.")).toBeVisible();
  await expect(page.locator(".mypage-summary strong")).toHaveText("바뀐이름");
  await expect(page.locator(".header-user")).toHaveText("바뀐이름님");
  await page.reload();
  await expect(page.locator(".mypage-summary")).toContainText("부산");
  await page.getByLabel("현재 비밀번호").fill("wrong-password-1");
  await page
    .getByLabel("새 비밀번호", { exact: true })
    .fill("second-password-2");
  await page.getByLabel("새 비밀번호 확인").fill("second-password-2");
  await page.getByRole("button", { name: "변경" }).click();
  await expect(page.getByText("현재 비밀번호가 맞지 않아요.")).toBeVisible();
  await page.getByLabel("현재 비밀번호").fill("first-password-1");
  await page.getByRole("button", { name: "변경" }).click();
  await expect(page.getByText("비밀번호를 바꿨어요.")).toBeVisible();
});
