import { test, expect } from "@playwright/test";
import { fixtureJobs, mockPublicJobs } from "./public-jobs-fixture";
import { catalogState, catalogUrl } from "../lib/catalog-navigation";
import { loginDestination } from "../lib/login-destination";

test("catalog state round trips and login destinations reject external or executable targets", () => {
  const state = catalogState(
    new URLSearchParams(
      "q=API&role=backend&location=서울&workplace=hybrid&experience=entry,experienced&sort=closing&limit=24&offset=48",
    ),
  );
  expect(
    catalogState(new URLSearchParams(catalogUrl(state).split("?")[1])),
  ).toEqual(state);
  for (const target of [
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/api/account",
    "javascript:alert(1)",
    "/jobs\n//evil.example",
  ])
    expect(loginDestination(target)).toBe("/analysis");
  expect(loginDestination("/jobs?job=fixture-0&view=stats")).toBe(
    "/jobs?job=fixture-0&view=stats",
  );
});

test("filters, page size, page and scroll survive a detail visit, refresh and browser back", async ({
  page,
}) => {
  await page.route("**/api/jobs?**", async (route) => {
    const p = new URL(route.request().url()).searchParams;
    const all = Array.from({ length: 60 }, (_, i) => ({
      ...fixtureJobs[0],
      id: "restore-" + i,
      title: "Backend restore " + i,
    }));
    const id = p.get("id"),
      offset = Number(p.get("offset") || 0),
      limit = Number(p.get("limit") || 12);
    const jobs = id
      ? all.filter((j) => j.id === id)
      : all.slice(offset, offset + limit);
    await route.fulfill({
      json: {
        jobs,
        total: id ? jobs.length : 60,
        nextOffset: offset + limit < 60 ? offset + limit : null,
        checkedAt: new Date().toISOString(),
        unavailableSources: [],
      },
    });
  });
  await page.goto("/jobs");
  await page.getByLabel("전체 연동 공고 검색").fill("Backend");
  await page.getByLabel("공고 직무", { exact: true }).selectOption("backend");
  await page.getByLabel("페이지당 공고 수").selectOption("24");
  await expect(page.locator(".job-list-row")).toHaveCount(24);
  await page
    .getByRole("button", { name: "2페이지로 이동", exact: true })
    .click();
  await expect(page.locator(".job-list-row h3").first()).toHaveText(
    "Backend restore 24",
  );
  const url = page.url();
  await page.locator(".job-list-row").nth(7).scrollIntoViewIfNeeded();
  const y = await page.evaluate(() => scrollY);
  await page.locator(".job-list-row").nth(7).locator(".card-link").click();
  await page.locator(".study-back").click();
  await expect(page).toHaveURL(url);
  await expect(page.locator(".job-list-row h3").first()).toHaveText(
    "Backend restore 24",
  );
  await expect
    .poll(() => page.evaluate(() => scrollY))
    .toBeGreaterThan(y - 100);
  await expect(page.getByLabel("전체 연동 공고 검색")).toHaveValue("Backend");
  await expect(page.getByLabel("페이지당 공고 수")).toHaveValue("24");
  await page.reload();
  await expect(page.locator(".job-list-row h3").first()).toHaveText(
    "Backend restore 24",
  );
  await page.locator(".job-list-row .card-link").first().click();
  await expect(page).toHaveURL(/job=restore-24/);
  await page.goBack();
  await expect(page.getByLabel("공고 직무", { exact: true })).toHaveValue(
    "backend",
  );
  await expect(page.locator(".job-list-row h3").first()).toHaveText(
    "Backend restore 24",
  );
});

test("save failures and success are visible; list errors retry without pretending to be empty", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.route("**/api/career", (route) =>
    route.fulfill({ json: { workspace: {} } }),
  );
  let broken = true;
  await page.route("**/api/saved-jobs", (route) =>
    route.fulfill(
      broken
        ? { status: 503, json: { error: "저장 서버에 연결하지 못했습니다." } }
        : { json: { jobs: [] } },
    ),
  );
  await page.goto("/jobs");
  await page.locator(".job-list-save").first().click();
  await expect(page.locator(".save-feedback[role=alert]")).toBeVisible();
  await page.locator(".save-feedback button").click();
  broken = false;
  await page.locator(".job-list-save").first().click();
  await expect(page.locator(".save-feedback[role=status]")).toContainText(
    "저장했어요",
  );
  broken = true;
  await page.goto("/my-page");
  await expect(
    page.getByRole("heading", { name: "저장 목록을 불러오지 못했습니다" }),
  ).toBeVisible();
  await expect(
    page.getByText("저장한 공고가 없어요.", { exact: true }),
  ).toHaveCount(0);
  broken = false;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(
    page.getByText("저장한 공고가 없어요.", { exact: true }),
  ).toBeVisible();
});

test("sign-in from a posting returns to that exact comparison after email login", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.route("**/api/account", (route) =>
    route.fulfill({
      json:
        route.request().method() === "POST"
          ? { user: { id: "mock-member", name: "검증" } }
          : { user: null, guest: false },
    }),
  );
  const destination = "/jobs?q=Backend&limit=24&job=fixture-0&view=stats";
  await page.goto(destination);
  await page.locator(".personal-comparison-message a").click();
  await expect(page).toHaveURL(new RegExp("/sign-in\\?next="));
  await expect(page.locator(".kakao-login-form input[name=next]")).toHaveValue(
    destination,
  );
  await page.getByLabel("이메일", { exact: true }).fill("ui-only@example.test");
  await page
    .getByLabel("비밀번호", { exact: true })
    .fill("not-a-real-account-password");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3000" + destination);
});
