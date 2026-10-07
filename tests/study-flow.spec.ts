import { test, expect, type Page } from "@playwright/test";
import { emptyWorkspace } from "../types/workspace";
import { fixtureJobs, mockPublicJobs } from "./public-jobs-fixture";
import AxeBuilder from "@axe-core/playwright";
import { jobExperience, sortPublicJobs } from "../lib/job-filters";

async function joinExample(page: Page, tier = "low") {
  await page.goto(`/jobs?job=study-demo-rag&demo=${tier}&view=study`);
  await expect(
    page.getByText("지원 완료를 확인하면 스터디를 볼 수 있어요"),
  ).toBeVisible();
  await page.getByLabel("예시 공고에 지원한 상태로 체험할게요").check();
  await page.getByRole("button", { name: "지원했어요", exact: true }).click();
  await expect(page.locator(".study-offer")).toHaveCount(2);
  await page
    .getByRole("button", { name: "참여 신청", exact: true })
    .first()
    .click();
  await page.getByRole("link", { name: "스터디 들어가기" }).click();
  await expect(page.getByText("나 1명", { exact: true })).toBeVisible();
}

test("official cards remain pending; only explicitly selected examples show satisfaction and skill levels", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/jobs");
  await expect(page.locator(".qualification-summary")).toHaveCount(7);
  await expect(page.locator(".qualification-heading").first()).toContainText(
    "자격요건 판정 대기",
  );
  await expect(page.locator(".qualification-skills")).toHaveCount(0);
  await page.getByRole("link", { name: "예시로 체험하기" }).click();
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
  await expect(first.locator(".qualification-skills")).toContainText("RAG LV2");
  await expect(first.locator(".qualification-skills")).not.toContainText("SQL");
  await expect(
    page.locator(".public-job-card").nth(1).locator(".qualification-skills"),
  ).toContainText("SQL LV2");
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

test("one member joins once, records roadmap, chat, schedule and resources, and persists after reload", async ({
  page,
}) => {
  await joinExample(page);
  const roomUrl = page.url();
  await page
    .getByRole("checkbox", { name: "완료 기록", exact: true })
    .first()
    .check();
  await expect(
    page.getByRole("progressbar", { name: "나의 과제 진행률" }),
  ).toHaveAttribute("value", "33");
  await page.getByRole("button", { name: "채팅", exact: true }).click();
  await page.getByLabel("채팅 메시지").fill("평가 결과를 함께 확인해요.");
  await page.getByRole("button", { name: "전송 · 체험" }).click();
  await expect(page.locator(".study-message")).toContainText(
    "평가 결과를 함께 확인해요.",
  );
  await page.getByRole("button", { name: "일정", exact: true }).click();
  await page.getByLabel("일정 이름").fill("결과 공유 모임");
  await page.getByLabel("날짜와 시간").fill("2026-10-10T19:00");
  await page.getByRole("button", { name: "일정 추가", exact: true }).click();
  await expect(page.locator(".study-item-list")).toContainText(
    "결과 공유 모임",
  );
  await page.getByRole("button", { name: "자료 공유", exact: true }).click();
  await page.getByLabel("자료 제목").fill("프로젝트 결과");
  await page.getByLabel("자료 링크").fill("https://example.com/results");
  await page.getByRole("button", { name: "자료 추가", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "프로젝트 결과" }),
  ).toHaveAttribute("href", "https://example.com/results");
  await page.reload();
  await expect(
    page.getByRole("progressbar", { name: "나의 과제 진행률" }),
  ).toHaveAttribute("value", "33");
  await page.getByRole("button", { name: "채팅", exact: true }).click();
  await expect(page.locator(".study-message")).toHaveCount(1);
  await page.getByRole("button", { name: "일정", exact: true }).click();
  await expect(page.locator(".study-item-list")).toContainText(
    "결과 공유 모임",
  );
  await page.getByRole("button", { name: "자료 공유", exact: true }).click();
  await expect(page.getByRole("link", { name: "프로젝트 결과" })).toBeVisible();
  await page.getByRole("link", { name: "내 스터디 목록", exact: true }).click();
  await expect(page.locator(".study-offer")).toHaveCount(1);
  await page.goto("/jobs?job=study-demo-rag&demo=low&view=study");
  await expect(page.getByRole("link", { name: "스터디 들어가기" })).toHaveCount(
    1,
  );
  await page.goto(roomUrl.replace("demo=low", "demo=middle"));
  await expect(
    page.getByText("이 체험에서 참여한 스터디가 아니에요"),
  ).toBeVisible();
  await expect(page.locator(".study-room")).toHaveCount(0);
});

test("each level sees only its own offers; High has a working roadmap; no leak to actual studies", async ({
  page,
}) => {
  await joinExample(page, "high");
  await expect(page.getByText("맞춤 심화 학습", { exact: true })).toBeVisible();
  await expect(page.locator(".study-roadmap li")).toHaveCount(3);
  await page.goto("/jobs?job=study-demo-rag&demo=high&view=study");
  await expect(page.locator(".study-offer .study-tier")).toHaveText([
    "High",
    "High",
  ]);
  await page.goto("/studies");
  await expect(page.locator(".study-offer")).toHaveCount(0);
  await expect(page.getByText("내가 참여한 스터디를 한곳에")).toBeVisible();
});

test("official application requires explicit confirmation and writes to existing application records", async ({
  page,
}) => {
  let workspace = structuredClone(emptyWorkspace);
  let writes = 0;
  await page.route("**/api/jobs?**", (route) =>
    route.fulfill({
      json: {
        jobs: [fixtureJobs[0]],
        total: 1,
        nextOffset: null,
        unavailableSources: [],
        checkedAt: new Date().toISOString(),
      },
    }),
  );
  await page.route("**/api/career", async (route) => {
    if (route.request().method() === "POST") {
      writes++;
      workspace = {
        ...workspace,
        applications: route.request().postDataJSON().applications,
      };
    }
    await route.fulfill({
      json: { user: { name: "게스트" }, guest: true, workspace },
    });
  });
  await page.goto("/jobs?job=fixture-0&view=study");
  await expect(
    page.getByRole("button", { name: "지원했어요", exact: true }),
  ).toBeDisabled();
  expect(writes).toBe(0);
  await page.getByLabel("이 공고에 지원을 완료했어요").check();
  await page.getByRole("button", { name: "지원했어요", exact: true }).click();
  await expect(page.getByText("지원 완료로 기록했어요")).toBeVisible();
  expect(writes).toBe(1);
  expect(workspace.applications[0].stage).toBe("지원 완료");
  await page.reload();
  await expect(page.getByText("지원 완료로 기록했어요")).toBeVisible();
  expect(writes).toBe(1);
  await expect(
    page.getByText("상대 수준 판정 대기", { exact: true }),
  ).toBeVisible();
});

test("study screens fit a mobile viewport and filters work with keyboard", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await joinExample(page, "middle");
  await expect(page.locator(".study-room")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "work/studies-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({ path: "work/studies-desktop.png", fullPage: true });
  await page.goto("/jobs?demo=middle");
  await expect(page.getByText("지원 완료 · 예시", { exact: true })).toBeVisible();
  const menu = page.locator("summary").filter({ hasText: "채용구분" });
  await menu.press("Enter");
  await expect(page.getByLabel("경력 무관", { exact: true })).toBeVisible();
  await menu.press("Enter");
  await page.screenshot({
    path: "work/jobs-study-comparison.png",
    fullPage: true,
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
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
