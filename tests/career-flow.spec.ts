import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("career:sky-intro:seen", "yes"),
  );
  await mockPublicJobs(page);
});

test("onboarding uses one source and carries target role into growth", async ({
  page,
}) => {
  await page.goto("/onboarding");
  await page.getByLabel("희망 직무").selectOption("ml");
  await page.getByRole("button", { name: "이 직무로 시작하기" }).click();
  await page.getByRole("button", { name: "GitHub 링크", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "자료에서 이런 기술을 찾았어요" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "내 성장 화면으로 이동하기" }).click();
  await page.goto("/skills");
  await expect(
    page.getByRole("heading", { name: "PyTorch", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "PyTorch", exact: true }),
  ).toBeVisible();
});

test("initial evidence is not rewarded and next task shows fixed points", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(page.locator(".growth-stats")).toContainText("0점");
  const card = page
    .locator(".growth-skill")
    .filter({
      has: page.getByRole("heading", { name: "Docker", exact: true }),
    });
  await expect(card).toContainText("LV1 · 기초 사용");
  await expect(card).toContainText("완료 확인 후 20점");
});

test("job analyzer matches samples, validates input, and has an empty state", async ({
  page,
}) => {
  await page.goto("/job-analyzer");
  await page.getByRole("button", { name: "분석하기", exact: true }).click();
  await expect(page.locator(".form-error[role=alert]")).toBeVisible();
  await page.getByLabel("채용공고 링크 또는 기업명").fill("NAVER");
  await page.getByRole("button", { name: "분석하기", exact: true }).click();
  await expect(page.locator(".analyzed-job h2")).toHaveText(
    "AI·머신러닝 엔지니어",
  );
  await expect(page.locator(".requirement-row")).toHaveCount(4);
  await page.getByLabel("채용공고 링크 또는 기업명").fill("Unlisted Company");
  await page.getByRole("button", { name: "분석하기", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "분석할 수 있는 예시 공고가 없어요." }),
  ).toBeVisible();
  await page
    .getByLabel("채용공고 링크 또는 기업명")
    .fill("https://www.lgcns.com/careers/demo");
  await page.getByRole("button", { name: "분석하기", exact: true }).click();
  await expect(page.locator(".analyzed-job h2")).toHaveText("AX·LLM 개발자");
});

test("skill correction is separate from level verification and rewards", async ({
  page,
}) => {
  await page.goto("/skills");
  const card = page
    .locator(".growth-skill")
    .filter({
      has: page.getByRole("heading", { name: "PostgreSQL", exact: true }),
    });
  await card.getByRole("button").click();
  await expect(page.getByRole("dialog")).toContainText("postgres");
  await page.getByRole("button", { name: "결과 확인했어요" }).click();
  await page.keyboard.press("Escape");
  await expect(card).toContainText("결과 확인함");
  await expect(card).toContainText("확인할 자료가 부족해요");
  await page.reload();
  await expect(card).toContainText("결과 확인함");
});

test("application detail, filtering and local record", async ({ page }) => {
  await page.goto("/applications");
  await page.getByRole("button", { name: "LG CNS 지원 기록 보기" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByText("지원 당시의 역량", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "닫기", exact: true }).click();
  await page.getByRole("button", { name: "지원 기록 추가" }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("combobox", { name: "지원 공고", exact: true })
    .selectOption("toss-ax");
  await dialog
    .getByRole("combobox", { name: "진행 단계", exact: true })
    .selectOption("Final");
  await dialog.getByRole("button", { name: "지원 기록 저장" }).click();
  await page.getByRole("button", { name: "최종 전형", exact: true }).click();
  await expect(page.locator(".application-table tbody tr")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: /toss AI Application Engineer/ }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: /toss AI Application Engineer/ }),
  ).toBeVisible();
});

test("all routes render without errors or mobile horizontal overflow", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of [
    "/",
    "/onboarding",
    "/dashboard",
    "/market",
    "/skills",
    "/agent",
    "/job-analyzer",
    "/applications",
    "/settings",
    "/profile",
    "/sign-in",
  ]) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();

    await expect
      .poll(
        () =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth + 1,
          ),
        { message: `Horizontal overflow at ${route}` },
      )
      .toBe(true);
  }
  expect(errors).toEqual([]);
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page.getByRole("link", { name: "채용시장", exact: true }).click();
  await expect(page).toHaveURL(/\/market$/);
  await expect(page.locator(".sidebar")).not.toHaveClass(/is-open/);
});

test("role and period filters change market data", async ({ page }) => {
  await page.goto("/market");
  await expect(page.getByText("387", { exact: true })).toBeVisible();
  await page.getByLabel("희망 직무").selectOption("data");
  await expect(page.getByText("312", { exact: true })).toBeVisible();
  await page.getByLabel("분석 기간").selectOption("6");
  await expect(
    page.getByText("2026년 4월~9월 · 예시 추이 데이터"),
  ).toBeVisible();
});

test("primary routes pass accessibility audit", async ({ page }) => {
  for (const route of [
    "/",
    "/dashboard",
    "/skills",
    "/agent",
    "/job-analyzer",
    "/applications",
  ]) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.locator("h1")).toHaveCSS("opacity", "1");
    await page.locator("h1").evaluate(async (el) => {
      await Promise.all(
        el.getAnimations({ subtree: true }).map((a) => a.finished),
      );
    });
    await expect(page.locator("h1").locator("..")).toHaveCSS("opacity", "1");
    await expect
      .poll(() =>
        page.locator("h1").evaluate((el) => {
          let node: Element | null = el;
          while (node) {
            if (Number(getComputedStyle(node).opacity) < 1) return false;
            node = node.parentElement;
          }
          return true;
        }),
      )
      .toBe(true);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect
      .soft(
        result.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes
            .map((n) => ({ target: n.target, summary: n.failureSummary }))
            .slice(0, 12),
        })),
        route,
      )
      .toEqual([]);
  }
});

test("level and pending filters preserve uncertainty", async ({ page }) => {
  await page.goto("/skills");
  await page.getByLabel("보기", { exact: true }).selectOption("pending");
  await expect(page.locator(".growth-skill")).toHaveCount(1);
  await expect(page.locator(".growth-skill")).toContainText("PostgreSQL");
  await page.getByLabel("보기", { exact: true }).selectOption("2");
  await expect(page.locator(".growth-skill")).toHaveCount(1);
  await expect(page.locator(".growth-skill")).toContainText("Python");
});

test("responsive layouts and chart rendering", async ({ page }, testInfo) => {
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of [
      "/",
      "/onboarding",
      "/dashboard",
      "/market",
      "/skills",
      "/agent",
      "/job-analyzer",
      "/applications",
    ]) {
      await page.goto(route);
      await expect(page.locator("h1")).toBeVisible();
      await expect
        .poll(
          () =>
            page.evaluate(
              () =>
                document.documentElement.scrollWidth <= window.innerWidth + 1,
            ),
          { message: `Overflow at ${width}px ${route}` },
        )
        .toBe(true);
      if (route === "/dashboard") {
        await expect(page.locator(".growth-skill")).toHaveCount(4);
        await page.screenshot({
          path: testInfo.outputPath(`dashboard-${width}.png`),
          fullPage: true,
        });
      }
      if (route === "/") {
        await expect(page.locator(".sky-home")).toHaveCSS("opacity", "1");
        await page.screenshot({
          path: testInfo.outputPath(`landing-${width}.png`),
          fullPage: true,
        });
      }
    }
  }
});
