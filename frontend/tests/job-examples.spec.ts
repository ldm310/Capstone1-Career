import { test, expect } from "@playwright/test";
import { mockPublicJobs } from "./public-jobs-fixture";
import { jobExperience, sortPublicJobs } from "../lib/job-filters";

test("official cards show no verdict; only explicitly selected examples show satisfaction and skill levels", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/jobs");
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await expect(page.locator(".qualification-summary")).toHaveCount(0);
  await page.getByRole("link", { name: "예시 보기" }).click();
  await expect(page.locator(".qualification-heading").first()).toContainText(
    "만족",
  );
  await expect(page.locator(".qualification-heading").nth(1)).toContainText(
    "불만족",
  );
  await page
    .getByRole("navigation", { name: "예시 수준 선택" })
    .getByRole("link", { name: "Middle", exact: true })
    .click();
  const first = page.locator(".public-job-card").first();
  await expect(first.locator(".qualification-skills")).toHaveCount(0);
  await expect(
    page.getByRole("option", { name: "인기순", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("option", { name: "추천순", exact: true }),
  ).toHaveCount(0);
});

test("recruitment multi-select and closing order filter examples with reset", async ({
  page,
}) => {
  await page.goto("/jobs?demo=low");
  await page.locator("summary").filter({ hasText: "채용구분" }).click();
  await page.getByLabel("신입", { exact: true }).check();
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await page.getByLabel("인턴", { exact: true }).check();
  await expect(page.locator(".public-job-card")).toHaveCount(2);
  await page.getByRole("button", { name: "필터 초기화", exact: true }).click();
  await expect(page.locator(".public-job-card")).toHaveCount(3);
  await page.getByLabel("공고 정렬").selectOption("closing");
  await expect(page.locator(".public-job-card h3").first()).toHaveText(
    "데이터 파이프라인 엔지니어",
  );
  await page.locator("summary").filter({ hasText: "상세조건" }).click();
  await page.getByLabel("지역 검색").fill("판교");
  await expect(page.locator(".public-job-card")).toHaveCount(1);
});

test("job detail uses category stats tabs and preserves the original posting", async ({
  page,
}) => {
  await page.goto("/jobs?job=study-demo-backend&demo=low");
  await expect(
    page.getByRole("navigation", { name: "공고 상세 메뉴" }).getByRole("link"),
  ).toHaveText(["공고 내용", "역량 비교"]);
  await expect(page.locator(".job-public-content")).toBeVisible();
  await expect(page.locator(".applicant-stats")).toHaveCount(0);
  await expect(page.locator(".job-posting-section h3")).toHaveText([
    "주요 업무",
    "자격요건",
    "우대사항",
    "근무 조건",
  ]);
});

test("unknown employment and deadlines are not fabricated", () => {
  expect(jobExperience({ title: "AI Engineer", employment: "정규직" })).toEqual(
    [],
  );
  expect(
    jobExperience({ title: "신입/경력 개발자", employment: "정규직" }),
  ).toEqual(["any", "entry", "experienced"]);
  const base = { postedAt: null, company: "테스트" };
  expect(
    sortPublicJobs(
      [
        { ...base, id: "unknown" },
        { ...base, id: "later", closesAt: "2026-10-20T00:00:00Z" },
        { ...base, id: "sooner", closesAt: "2026-10-10T00:00:00Z" },
      ],
      "closing",
    ).map((j) => j.id),
  ).toEqual(["sooner", "later", "unknown"]);
});

test("dummy detail opens stats first and condition info separately", async ({
  page,
}) => {
  await page.goto("/jobs?job=dummy%3Abackend-platform");
  await expect(page.locator(".job-public-content")).toBeVisible();
  await expect(page.locator(".job-posting-section h3").first()).toHaveText(
    "회사 소개",
  );
  await expect(page.locator(".job-original-link")).toHaveAttribute(
    "href",
    /^\/postings\//,
  );
  await page.getByRole("link", { name: "역량 비교", exact: true }).click();
  await expect(page.locator(".personal-job-comparison")).toBeVisible();
  await expect(page.locator(".category-radar")).toHaveCount(0);
});

test("detail omits lower bars while catalog keeps the cohort average", async ({
  page,
}) => {
  await page.goto("/jobs?job=dummy%3Abackend-platform");
  await expect(page.locator(".job-public-content")).toBeVisible();
  await expect(
    page.locator(".passed-preferred, .applicant-stats, [role=progressbar]"),
  ).toHaveCount(0);
  await mockPublicJobs(page);
  await page.goto("/jobs");
  await expect(
    page.locator(".public-job-card .passed-gap").first(),
  ).toContainText("공고의 역량 키워드와 내 경험을 비교해요");
});

test("dummy jobs link to a placeholder original; real jobs without a link say so", async ({
  page,
}) => {
  await page.goto("/jobs?job=dummy%3Adata-engineer");
  const original = page.locator(".job-original-link");
  await expect(original).toHaveAttribute(
    "href",
    "/postings/dummy%3Adata-engineer",
  );
  const posting = await page.request.get("/postings/dummy%3Adata-engineer");
  expect(await posting.text()).toContain("예시 원문 페이지예요");
  await page.route("**/api/jobs?**", (route) =>
    route.fulfill({
      json: {
        jobs: [
          {
            id: "no-link",
            company: "테스트",
            title: "링크 없는 공고",
            category: "backend",
            location: "서울",
            employment: "정규직",
            workplace: null,
            postedAt: null,
            url: "",
          },
        ],
        total: 1,
        nextOffset: null,
        checkedAt: new Date().toISOString(),
        unavailableSources: [],
      },
    }),
  );
  await page.goto("/jobs?job=no-link");
  await expect(page.locator(".job-source-row .original-missing")).toHaveText(
    "원문을 찾을 수 없습니다.",
  );
});
