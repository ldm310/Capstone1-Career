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
      name: "Machine Learning Engineer 1 저장",
      exact: true,
    })
    .click();

  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await expect(
    page.getByText("현재 제공되는 공고를 모두 확인했어요."),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "채용공고 하위 메뉴" })
    .getByRole("link", { name: "저장한 공고" })
    .click();
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Machine Learning Engineer 1 저장 취소" }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("navigation", { name: "채용공고 하위 메뉴" })
    .getByRole("link", { name: "전체 공고", exact: true })
    .click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.locator(".public-job-card")).toHaveCount(7);
  await page.getByLabel("공고 직무").selectOption("ax");
  await expect(page.locator(".public-job-card")).toHaveCount(1);
  await expect(page.locator(".public-job-card h3")).toHaveText(
    "Applied AI Engineer 7",
  );
  await page.getByLabel("전체 연동 공고 검색").fill("없는기업");
  await expect(page.getByText("조건에 맞는 공고가 없어요.")).toBeVisible();
});
test("job errors retry and partial availability remains explicit", async ({
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
  await expect(
    page.getByText(/매치그룹 공고는 일시적으로 연결되지 않았어요/),
  ).toBeVisible();
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
