import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockPublicJobs } from "./public-jobs-fixture";

const pdf = {
  name: "resume.pdf",
  mimeType: "application/pdf",
  buffer: Buffer.from("%PDF-1.4 fictional resume fixture"),
};
async function prepare(page: Page) {
  await page.route("**/api/account", (route) =>
    route.fulfill({
      json: { user: { id: "test-member", name: "테스트 회원" }, guest: false },
    }),
  );
  await page.route("**/api/career", (route) =>
    route.fulfill({ json: { workspace: { runs: [], documents: [] } } }),
  );
  await mockPublicJobs(page);
}
async function addGithub(page: Page, name: string) {
  await page
    .getByLabel("공개 GitHub 저장소 URL")
    .fill(`https://github.com/example/${name}`);
  await page.getByRole("button", { name: "링크 추가", exact: true }).click();
}

test("mixed sources are optional, multiple, submitted once and complete without a standalone LV result", async ({
  page,
}) => {
  await prepare(page);
  const sent: string[] = [];
  await page.route("**/api/analyze", async (route) => {
    sent.push(route.request().postDataJSON().url);
    await route.fulfill({ json: { workspace: { runs: [] } } });
  });
  await page.route("**/api/documents", async (route) => {
    sent.push("pdf");
    await route.fulfill({ json: { workspace: { runs: [] } } });
  });
  await page.goto("/analysis");
  const start = page.getByRole("button", {
    name: "분석 시작하기",
    exact: true,
  });
  await expect(start).toBeDisabled();
  await addGithub(page, "one");
  await expect(start).toBeEnabled();
  await addGithub(page, "two");
  await page
    .getByLabel("PDF 이력서 추가")
    .setInputFiles([pdf, { ...pdf, name: "resume-2.pdf" }]);
  await expect(page.locator(".analysis-source-list li")).toHaveCount(4);
  await page.screenshot({ path: "work/analysis-sources.png", fullPage: true });
  await start.click();
  await expect(
    page.getByRole("heading", { name: "분석 완료!", exact: true }),
  ).toBeVisible();
  expect(sent).toEqual([
    "https://github.com/example/one",
    "https://github.com/example/two",
    "pdf",
    "pdf",
  ]);
  await expect(page.locator(".analysis-complete")).not.toContainText(
    /LV|SQL|React/,
  );
  await page.screenshot({ path: "work/analysis-complete.png", fullPage: true });
  await page
    .getByRole("link", { name: "채용공고에서 내 역량 확인하기" })
    .click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.locator(".job-list-row")).toHaveCount(7);
});

test("a PDF alone is sufficient and unsupported, duplicate and oversized sources are rejected", async ({
  page,
}) => {
  await prepare(page);
  await page.route("**/api/documents", (route) =>
    route.fulfill({ json: { workspace: { runs: [] } } }),
  );
  await page.goto("/analysis");
  const files = page.getByLabel("PDF 이력서 추가");
  await files.setInputFiles({
    name: "resume.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("text"),
  });
  await expect(page.locator(".analysis-error")).toContainText("PDF 파일만");
  await expect(page.locator(".analysis-source-list li")).toHaveCount(0);
  await files.setInputFiles({ ...pdf, buffer: Buffer.alloc(10_000_001) });
  await expect(page.locator(".analysis-error")).toContainText("10MB 이하");
  await files.setInputFiles(pdf);
  await expect(page.locator(".analysis-source-list li")).toHaveCount(1);
  await page
    .getByRole("button", { name: "분석 시작하기", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "분석 완료!", exact: true }),
  ).toBeVisible();
});

test("partial failures retry only failed sources and never report full completion early", async ({
  page,
}) => {
  await prepare(page);
  const sent: string[] = [];
  let failing = true;
  await page.route("**/api/analyze", async (route) => {
    const url = route.request().postDataJSON().url as string;
    sent.push(url);
    await route.fulfill(
      failing && url.endsWith("two")
        ? { status: 502, json: { error: "저장소 연결 실패" } }
        : { json: { workspace: { runs: [] } } },
    );
  });
  await page.goto("/analysis");
  await addGithub(page, "one");
  await addGithub(page, "one");
  await expect(page.locator(".analysis-error")).toContainText("이미 추가");
  await addGithub(page, "two");
  await page
    .getByRole("button", { name: "분석 시작하기", exact: true })
    .click();
  await expect(page.locator(".analysis-error")).toContainText("일부 자료");
  await expect(
    page.getByRole("heading", { name: "분석 완료!", exact: true }),
  ).toHaveCount(0);
  failing = false;
  await page.getByRole("button", { name: "실패한 자료 다시 분석하기" }).click();
  await expect(
    page.getByRole("heading", { name: "분석 완료!", exact: true }),
  ).toBeVisible();
  expect(sent).toEqual([
    "https://github.com/example/one",
    "https://github.com/example/two",
    "https://github.com/example/two",
  ]);
});

test("public jobs and home need no session, old skills URLs redirect, and analysis works on mobile", async ({
  page,
}) => {
  await mockPublicJobs(page);
  let guestRequests = 0;
  await page.route("**/api/career", (route) =>
    route.fulfill({ status: 401, json: { error: "Unauthorized" } }),
  );
  await page.route("**/api/guest", (route) => {
    guestRequests++;
    return route.fulfill({ status: 500 });
  });
  await page.goto("/#market-preview");
  await expect(
    page.getByRole("navigation", { name: "주 메뉴" }).getByRole("link"),
  ).toHaveText(["홈", "채용공고", "분석"]);
  await expect(page.locator(".home-radar")).toHaveCount(0);
  await page.goto("/my-skills");
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.locator(".job-list-row")).toHaveCount(7);
  await page.goto("/my-data");
  await expect(page).toHaveURL(/\/analysis$/);
  for (const width of [768, 390, 320]) {
    await page.setViewportSize({ width, height: 960 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({ path: "work/analysis-mobile.png", fullPage: true });
  expect(guestRequests).toBe(0);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});

test("documents API rejects renamed text and Markdown even when called directly", async ({
  request,
}) => {
  const headers = { origin: "http://127.0.0.1:3000" };
  await request.post("/api/account", {
    headers,
    data: {
      action: "register",
      email: `pdf-test-${Date.now()}@example.com`,
      password: "Career-test-2026!",
      name: "PDF 테스트",
    },
  });
  for (const name of ["resume.pdf", "resume.md"]) {
    const response = await request.post("/api/documents", {
      headers,
      multipart: {
        file: {
          name,
          mimeType: "application/pdf",
          buffer: Buffer.from("Not a PDF, just text"),
        },
      },
    });
    expect(response.ok()).toBe(false);
    expect((await response.json()).error).toContain("PDF");
  }
});
