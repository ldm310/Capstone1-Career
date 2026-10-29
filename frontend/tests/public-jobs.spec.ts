import { test, expect } from "@playwright/test";
import { mockPublicJobs } from "./public-jobs-fixture";
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("career:sky-intro:seen", "yes"),
  );
});
test("official job cards paginate, bookmark, persist, filter and link to source", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/jobs");
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await expect(page.locator(".public-job-source").first()).toHaveAttribute(
    "href",
    "https://jobs.lever.co/zoyi/fixture-0",
  );
  await expect(page.locator(".public-job-source").first()).toHaveAttribute(
    "target",
    "_blank",
  );
  await page
    .getByRole("button", {
      name: "Backend Engineer 1 저장",
      exact: true,
    })
    .click();

  await expect(
    page.getByRole("button", { name: "Backend Engineer 1 저장 취소" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await expect(page.getByText("모든 공고를 확인했어요.")).toBeVisible();
  // 저장한 공고는 마이페이지에서 본다. 예전 주소도 마이페이지로 보낸다.
  await page.goto("/jobs?tab=saved");
  await expect(page).toHaveURL(/\/my-page$/);
  await expect(page.locator(".mypage-jobs li")).toHaveCount(1);
  await expect(page.locator(".mypage-jobs h3")).toHaveText(
    "Backend Engineer 1",
  );
  await page.reload();
  await expect(page.locator(".mypage-jobs li")).toHaveCount(1);
  await page.goto("/jobs");
  await expect(
    page.getByRole("button", { name: "Backend Engineer 1 저장 취소" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await page.getByLabel("공고 직무").selectOption("data");
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await expect(page.locator(".public-job-card h3")).toHaveText(
    "Data Engineer 7",
  );
  await page.getByLabel("전체 연동 공고 검색").fill("없는기업");
  await expect(page.getByText("조건에 맞는 공고가 없어요.")).toBeVisible();
});
test("job errors retry and unavailable sources stay hidden", async ({
  page,
}) => {
  let failed = true;
  await page.route("**/api/jobs?**", async (route) =>
    failed
      ? route.fulfill({ status: 502, json: { error: "unavailable" } })
      : route.fulfill({
          json: {
            jobs: [],
            total: 0,
            nextOffset: null,
            checkedAt: "2026-09-25T10:00:00Z",
            unavailableSources: ["매치그룹"],
          },
        }),
  );
  await page.goto("/jobs");
  await expect(page.locator(".public-job-empty[role=alert]")).toBeVisible();
  failed = false;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.getByText(/공고를 불러오지 못했어요/)).toHaveCount(0);
  await expect(page.getByText("조건에 맞는 공고가 없어요.")).toBeVisible();
});
test("public jobs API rejects invalid filters before contacting sources", async ({
  request,
}) => {
  for (const query of ["offset=-1", "limit=0", "role=unknown", "offset=abc"]) {
    const response = await request.get(`/api/jobs?${query}`);
    expect(response.status()).toBe(400);
  }
});
