import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { emptyWorkspace, type Workspace } from "@/types/workspace";
import { connectJobEvidence } from "@/lib/job-evidence";
import examples from "@/mock/reviewed-keyword-examples.json";

const detail = "/jobs?job=study-demo-backend&demo=low";
const screenshotStyle = ".site-header, .skip-link, nextjs-portal { visibility: hidden !important; }";
const myWorkspace: Workspace = {
  ...emptyWorkspace,
  runs: [
    {
      id: "my-pdf",
      sourceId: "document:my-pdf",
      title: "내 이력서.pdf",
      at: "2026-11-22",
      findings: [
        {
          id: "my-evidence",
          skill: "PostgreSQL",
          type: "career",
          title: "내 이력서.pdf",
          quote: "PostgreSQL 인덱스와 쿼리를 개선했습니다.",
          url: "/documents/my-pdf",
          detectedAt: "2026-11-22",
        },
      ],
    },
  ],
};
async function account(
  page: Page,
  member: boolean,
  workspace = emptyWorkspace,
) {
  await page.route("**/api/account", (route) =>
    route.fulfill({
      json: {
        user: member ? { id: "me", name: "검수 회원" } : null,
        guest: false,
      },
    }),
  );
  await page.route("**/api/career", (route) =>
    route.fulfill({ json: { workspace } }),
  );
  await page.route("**/api/growth", (route) =>
    route.fulfill({ json: { growth: { reviews: [], tasks: [] } } }),
  );
}

test("public posting and requirements stay open without login or private data requests", async ({
  page,
}) => {
  await page.setViewportSize({ width: 520, height: 950 });
  await account(page, false);
  let privateRequests = 0;
  page.on("request", (request) => {
    if (/\/api\/(career|growth)$/.test(request.url())) privateRequests++;
  });
  await page.goto(detail);
  await expect(
    page.locator("#job-public-content .job-posting-section"),
  ).toHaveCount(4);
  await expect(
    page.getByRole("navigation", { name: "공고 상세 메뉴" }).getByRole("link"),
  ).toHaveText(["공고 내용", "역량 비교"]);
  await expect(
    page.getByRole("heading", { name: "개인 역량 비교 로그인", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".personal-keyword-list > li")).toHaveCount(6);
  await expect(page.locator(".personal-keyword-level")).toHaveCount(0);
  await expect(page.locator(".personal-radar-card")).toHaveCount(0);
  expect(privateRequests).toBe(0);
  await page.screenshot({ path: "work/job-review-public.png", fullPage: true, style: screenshotStyle });
});

test("member without sources sees a local comparison prompt while public posting stays visible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 520, height: 950 });
  await account(page, true);
  await page.goto(detail);
  await expect(
    page.getByRole("heading", { name: "분석 자료 미등록", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#job-public-content")).toBeVisible();
  await expect(page.locator(".personal-radar-card")).toHaveCount(0);
  await expect(page.locator(".personal-keyword-level")).toHaveCount(0);
  await page.locator(".personal-job-comparison").screenshot({
    path: "work/job-review-no-sources.png",
    style: screenshotStyle,
  });
});

test("own PDF findings drive this posting's visualization and evidence without synthetic my scores", async ({
  page,
}) => {
  await page.setViewportSize({ width: 520, height: 950 });
  await account(page, true, myWorkspace);
  await page.goto(detail);
  await expect(page.locator(".personal-comparison-summary")).toContainText(
    "내 분석 자료 1개",
  );
  await expect(page.locator(".personal-comparison-summary")).toContainText(
    "근거 후보 1개",
  );
  await expect(page.locator(".personal-radar-card svg")).toHaveCount(1);
  await expect(page.locator(".personal-radar-card")).toContainText(
    "LV·합격 점수가 아닙니다",
  );
  const requirement = page
    .locator(".personal-keyword-list > li")
    .filter({ hasText: "PostgreSQL 또는 MariaDB" });
  await requirement.locator("summary").click();
  await expect(requirement).toContainText("내 이력서.pdf");
  await expect(requirement).toContainText("인덱스와 쿼리를 개선");
  await expect(requirement.locator(".personal-keyword-level")).toContainText(
    "산정 전",
  );
  await expect(page.getByText("내 LV도 예시로 표시해요.")).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.locator(".personal-job-comparison").screenshot({
    path: "work/job-review-own-sources.png",
    style: screenshotStyle,
  });
});

test("confirmed scores apply only to the exact posting keyword with owned evidence", async ({
  page,
}) => {
  await account(page, true, myWorkspace);
  const keyword = examples.examples.find((item) =>
    item.categoryCodes.includes("D"),
  )!;
  await page.route("**/api/growth", (route) =>
    route.fulfill({
      json: {
        growth: {
          reviews: [
            {
              skill: keyword.id,
              original: keyword.id,
              level: 3,
              status: "confirmed",
              score: 72,
              evidenceIds: ["my-evidence"],
              reason: "reviewed",
            },
          ],
          tasks: [],
        },
      },
    }),
  );
  await page.goto(detail);
  await expect(
    page.getByRole("heading", { name: "공고별 내 역량", exact: true }),
  ).toBeVisible();
  const row = page
    .locator(".personal-keyword-list > li")
    .filter({ hasText: keyword.text });
  await expect(row.locator(".personal-keyword-level")).toContainText("72");
  await expect(row.locator(".personal-keyword-level")).toContainText(
    "평가 완료",
  );
});

test("private comparison failures cannot hide public posting contents", async ({
  page,
}) => {
  await account(page, true, myWorkspace);
  await page.route("**/api/career", (route) =>
    route.fulfill({ status: 503, json: { error: "Unavailable" } }),
  );
  await page.goto(detail);
  await expect(
    page.locator(".personal-comparison-message[role=alert]"),
  ).toContainText("공고는 계속 열람");
  await expect(
    page.locator("#job-public-content .job-posting-section"),
  ).toHaveCount(4);
  await expect(page).toHaveURL(/\/jobs\?/);
});

test("different posting requirements produce different matches for the same member", async ({
  page,
}) => {
  await account(page, true, myWorkspace);
  await page.route("**/api/jobs/keywords?**", (route) => {
    const id = new URL(route.request().url()).searchParams.get("jobId");
    return route.fulfill({
      json: {
        source: "SAVED_REVIEW",
        keywords: examples.examples.filter((keyword) =>
          keyword.categoryCodes.includes(id === "study-demo-data" ? "D" : "B"),
        ),
      },
    });
  });
  await page.goto(detail);
  await expect(page.locator(".personal-comparison-summary")).toContainText(
    "근거 후보 0개",
  );
  await page.goto("/jobs?job=study-demo-data&demo=low");
  await expect(page.locator(".personal-comparison-summary")).toContainText(
    "근거 후보 1개",
  );
});

test("old technology scores cannot become keyword LVs, exact reviewed scores need owned evidence", () => {
  const keyword = examples.examples.find((item) =>
    item.categoryCodes.includes("D"),
  )!;
  const finding = myWorkspace.runs[0].findings[0];
  const review = {
    skill: "PostgreSQL",
    original: "PostgreSQL",
    level: 3 as const,
    status: "confirmed" as const,
    score: 95,
    evidenceIds: [finding.id],
    reason: "reviewed",
  };
  expect(
    connectJobEvidence([keyword], [finding], [review])[0].myLevel,
  ).toBeNull();
  expect(
    connectJobEvidence(
      [keyword],
      [finding],
      [{ ...review, skill: keyword.id, score: 72 }],
    )[0].myLevel,
  ).toBe(72);
  expect(
    connectJobEvidence([keyword], [], [{ ...review, skill: keyword.id }])[0]
      .myLevel,
  ).toBeNull();
});

test("member comparison fits mobile and remains accessible", async ({
  page,
}) => {
  await account(page, true, myWorkspace);
  await page.goto(detail);
  await expect(page.locator(".personal-radar-card svg")).toHaveCount(1);
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 950 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({ path: "work/job-review-mobile.png", fullPage: true });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});
