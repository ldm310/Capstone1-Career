import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";

test("home previews are compact and each card opens its independent section", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/#features");
  await expect(page.locator(".public-job-card")).toHaveCount(3);
  await expect(page.getByLabel("공고 직무")).toHaveCount(0);
  const sections = [
    [
      "공고 찾아보기",
      "/jobs",
      "채용공고",
      ["전체 공고", "저장한 공고", "내 역량과 비교"],
    ],
    [
      "내 자료로 시작하기",
      "/my-skills",
      "내 역량 확인",
      ["자료 추가", "분석 결과·근거", "포트폴리오 공유"],
    ],
    [
      "필요한 준비 보기",
      "/preparation",
      "취업 준비",
      ["다음 과제 찾기", "진행 중인 과제", "주간 계획", "면접 준비"],
    ],
    [
      "지원 기록 보기",
      "/application-tracker",
      "지원 관리",
      ["지원·이력서", "일정·마감"],
    ],
    [
      "성장 기록 보기",
      "/growth",
      "성장 대시보드",
      ["성장 현황", "완료·포인트 내역", "성장 랭킹"],
    ],
  ] as const;
  for (const [action, url, title, tabs] of sections) {
    await page.goto("/#features");
    await page
      .locator(".home-feature-card")
      .filter({ hasText: action })
      .click();
    await expect(page).toHaveURL(new RegExp(url + "$"));
    await expect(
      page.getByRole("heading", { level: 1, name: title, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".sidebar")).toHaveCount(0);
    await expect(
      page
        .getByRole("navigation", { name: title + " 하위 메뉴" })
        .getByRole("link"),
    ).toHaveText([...tabs]);
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 960 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${url} width ${width}`,
      ).toBe(true);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    const a = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(a.violations, url).toEqual([]);
  }
});

test("catalog filters, saved-only view and comparison URL stay inside jobs", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/jobs");
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await page
    .getByRole("button", {
      name: "Machine Learning Engineer 1 저장",
      exact: true,
    })
    .click();
  await page
    .getByRole("navigation", { name: "채용공고 하위 메뉴" })
    .getByRole("link", { name: "저장한 공고" })
    .click();
  await expect(page).toHaveURL(/\/jobs\?tab=saved$/);
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await page.locator("summary").filter({ hasText: "상세조건" }).click();
  await page.getByLabel("근무 방식").selectOption("hybrid");
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await page.getByLabel("지역 검색").fill("부산");
  await expect(page.locator(".public-job-card")).toHaveCount(0);
  await page.getByRole("button", { name: "필터 초기화" }).click();
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await page.getByRole("link", { name: "내 실제 자료와 비교하기 →" }).click();
  await expect(page).toHaveURL(/\/jobs\?tab=jobs&url=/);
  await expect(
    page.getByRole("heading", { name: "공고의 요구 조건과 내 근거 비교" }),
  ).toBeVisible();
  await expect(page.getByLabel("공고 URL")).toHaveValue(
    "https://jobs.lever.co/zoyi/fixture-0",
  );
});

test("old links preserve destination and unrelated tabs cannot leak into sections", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/career?tab=schedule");
  await expect(page).toHaveURL(/\/application-tracker\?tab=schedule$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "지원 관리" }),
  ).toBeVisible();
  await page.goto("/my-skills?tab=schedule");
  await expect(
    page.getByRole("heading", { name: "지금까지 해온 것을 알려주세요" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "내 역량 확인 하위 메뉴" })
      .getByRole("link", { name: "일정·마감" }),
  ).toHaveCount(0);
});

test("catalog loads more than one page and filters send complete query to API", async ({
  page,
}) => {
  const rows = Array.from({ length: 17 }, (_, i) => ({
    id: `more-${i}`,
    company: "검증 회사",
    title: `AI 개발자 ${i + 1}`,
    category: "ml",
    location: "서울",
    employment: "정규직",
    workplace: "하이브리드 근무",
    postedAt: "2026-09-29T00:00:00Z",
    url: `https://jobs.lever.co/zoyi/more-${i}`,
    skills: ["Python"],
  }));
  await page.route("**/api/jobs?**", async (route) => {
    const p = new URL(route.request().url()).searchParams;
    const offset = Number(p.get("offset")),
      limit = Number(p.get("limit"));
    await route.fulfill({
      json: {
        jobs: rows.slice(offset, offset + limit),
        total: rows.length,
        nextOffset: offset + limit < rows.length ? offset + limit : null,
        checkedAt: new Date().toISOString(),
        unavailableSources: [],
      },
    });
  });
  await page.goto("/jobs");
  await expect(page.locator(".public-job-card")).toHaveCount(12);
  await page.getByRole("button", { name: "새로운 공고 더보기" }).click();
  await expect(page.locator(".public-job-card")).toHaveCount(17);
  const request = page.waitForRequest(
    (r) =>
      r.url().includes("/api/jobs?") &&
      new URL(r.url()).searchParams.get("q") === "Python",
  );
  await page.getByLabel("전체 연동 공고 검색").fill("Python");
  await request;
  await expect(page.locator(".public-job-card")).toHaveCount(12);
});
