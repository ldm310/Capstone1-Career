import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { emptyWorkspace, type Workspace } from "@/types/workspace";
import { connectJobEvidence } from "@/lib/job-evidence";
import examples from "@/mock/reviewed-keyword-examples.json";

const posting = "/jobs?job=study-demo-backend&demo=low";
const analysis = posting + "&view=stats";
const myWorkspace: Workspace = {
  ...emptyWorkspace,
  runs: [
    {
      id: "my-pdf",
      title: "내 이력서.pdf",
      at: "2026-11-23",
      findings: [
        {
          id: "my-evidence",
          skill: "PostgreSQL",
          type: "career",
          title: "내 이력서.pdf",
          quote: "PostgreSQL 인덱스와 쿼리를 개선했습니다.",
          url: "/documents/my-pdf",
          detectedAt: "2026-11-23",
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
  await page.route("**/api/jobs/my-levels?**", (route) =>
    route.fulfill({ status: 503, json: { error: "Not configured" } }),
  );
}

test("public posting and analysis are separate tabs, not scroll anchors", async ({
  page,
}) => {
  await account(page, false);
  let privateRequests = 0;
  page.on("request", (request) => {
    if (/\/api\/(career|growth|jobs\/my-levels)/.test(request.url()))
      privateRequests++;
  });
  await page.goto(posting);
  await expect(
    page.getByRole("tablist", { name: "공고 상세 메뉴" }).getByRole("tab"),
  ).toHaveText(["공고 내용", "역량 분석"]);
  await expect(page.locator(".job-posting-section")).toHaveCount(4);
  await expect(
    page.getByRole("heading", { name: "근무지 위치", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".personal-job-comparison")).toHaveCount(0);
  await expect(
    page.locator(".job-original-link, .original-missing"),
  ).toHaveCount(0);
  expect(privateRequests).toBe(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole("tab", { name: "역량 분석", exact: true }).click();
  await expect(page).toHaveURL(/view=stats$/);
  await expect(page.locator("#job-public-content")).toBeHidden();
  await expect(page.locator(".job-posting-section")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "개인 역량 분석", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".personal-keyword-list")).toHaveCount(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await page
    .getByRole("tab", { name: "역량 분석", exact: true })
    .press("ArrowLeft");
  await expect(
    page.getByRole("tab", { name: "공고 내용", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".job-posting-section")).toHaveCount(4);
  await expect(page.locator(".personal-job-comparison")).toHaveCount(0);
});

test("members without sources see only the registration prompt in analysis", async ({
  page,
}) => {
  await account(page, true);
  await page.goto(analysis);
  await expect(
    page.getByRole("heading", { name: "분석 자료 미등록", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#job-public-content")).toBeHidden();
  await expect(
    page.locator(".personal-radar-card, .personal-keyword-list"),
  ).toHaveCount(0);
});

test("unscored findings remain evidence coverage and the long keyword list is removed", async ({
  page,
}) => {
  await account(page, true, myWorkspace);
  await page.goto(analysis);
  await expect(page.locator(".personal-comparison-footer")).toContainText(
    "자료 추가",
  );
  await expect(page.locator(".personal-comparison-footer")).not.toContainText(
    "분석 자료 1개",
  );
  await expect(page.locator(".personal-radar-card")).toContainText(
    "LV, 합격 점수가 아닙니다",
  );
  await expect(
    page.locator(
      ".personal-keyword-list, .personal-keyword-level, .personal-keyword-evidence",
    ),
  ).toHaveCount(0);
});

test("exact confirmed sentence LV is visible on a chart point", async ({
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
  await page.goto(analysis);
  const point = page.locator(
    '.radar-point[aria-label="데이터베이스: 내 LV 72"]',
  );
  await point.focus();
  await expect(point.getByRole("tooltip")).toContainText("내 LV 72");
  await point.press("Escape");
  await expect(point.getByRole("tooltip")).toHaveCount(0);
});

test("private analysis errors do not prevent returning to the public posting", async ({
  page,
}) => {
  await account(page, true, myWorkspace);
  await page.route("**/api/career", (route) =>
    route.fulfill({ status: 503, json: { error: "Unavailable" } }),
  );
  await page.goto(analysis);
  await expect(
    page.locator(".personal-comparison-message[role=alert]"),
  ).toBeVisible();
  await page.getByRole("tab", { name: "공고 내용", exact: true }).click();
  await expect(page.locator(".job-posting-section")).toHaveCount(4);
  await expect(page.locator(".personal-job-comparison")).toHaveCount(0);
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

test("saved LV points show instant hover, keyboard and tap values without text lists", async ({
  page,
}) => {
  await account(page, true, myWorkspace);
  await page.route("**/api/jobs/my-levels?**", (route) =>
    route.fulfill({
      json: {
        jobId: "study-demo-backend",
        taxonomyVersion: examples.version,
        source: "RDS",
        sources: [
          { id: "demo-pdf", kind: "PDF", title: "이력서.pdf", simulated: true },
        ],
        levels: examples.examples.map((keyword, index) => ({
          keywordId: keyword.id,
          text: keyword.text,
          categoryCodes: keyword.categoryCodes,
          score: 30 + index * 7,
          referenceScore: 65 + index * 3,
          referenceKind: "SYNTHETIC_APPLICANTS",
          evaluationKind: "DEMO",
          evaluatedAt: "2026-11-23",
        })),
      },
    }),
  );
  await page.goto(analysis);
  const radar = page.getByTestId("saved-level-radar");
  await expect(radar).toBeVisible();
  const point = radar
    .locator(".radar-point")
    .filter({ has: page.locator('[data-series-point="mine"]') })
    .first();
  await point.hover();
  await expect(point.getByRole("tooltip")).toContainText(/내 LV \d+/);
  await page.mouse.move(0, 0);
  await point.focus();
  await expect(point.getByRole("tooltip")).toBeVisible();
  await point.press("Escape");
  await expect(point.getByRole("tooltip")).toHaveCount(0);
  await point.locator("circle").first().click();
  await expect(point.getByRole("tooltip")).toBeVisible();
  await expect(
    page.locator(
      ".personal-keyword-list, .job-posting-section, .job-original-link",
    ),
  ).toHaveCount(0);
  await page.mouse.move(0, 0);
  await page.getByRole("tab", { name: "역량 분석", exact: true }).focus();
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
});
