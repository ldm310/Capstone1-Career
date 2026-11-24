import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { mockPublicJobs } from "./public-jobs-fixture";

test("visitors can download both templates and browse jobs but cannot start extraction", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/analysis");
  await expect(page.getByText("회원 전용 분석")).toBeVisible();
  await expect(page.getByLabel("공개 GitHub 저장소 URL")).toBeDisabled();
  await expect(page.getByLabel("PDF 이력서 추가")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "분석 시작하기", exact: true }),
  ).toBeDisabled();
  const word = page.getByRole("link", {
    name: "Career 이력서 양식 다운로드, Word",
    exact: true,
  });
  const download = page.waitForEvent("download");
  await word.click();
  expect((await download).suggestedFilename()).toBe(
    "career-resume-template.docx",
  );
  const pdf = await page.request.get("/downloads/career-resume-template.pdf");
  expect(pdf.ok()).toBe(true);
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  await page.screenshot({
    path: "work/analysis-login-and-template.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 320, height: 900 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.goto("/jobs");
  await expect(page.locator(".job-list-row")).toHaveCount(7);
});

test("extraction APIs reject unauthenticated and guest requests before reading source data", async ({
  request,
  baseURL,
}) => {
  const headers = { Origin: baseURL! };
  for (const guest of [false, true]) {
    if (guest)
      expect((await request.post("/api/guest", { headers })).ok()).toBe(true);
    const github = await request.post("/api/analyze", {
      headers,
      data: { kind: "github", url: "https://github.com/example/private" },
    });
    expect(github.status()).toBe(401);
    const upload = await request.post("/api/documents", {
      headers,
      multipart: {
        file: {
          name: "resume.pdf",
          mimeType: "application/pdf",
          buffer: Buffer.from("%PDF-fixture"),
        },
      },
    });
    expect(upload.status()).toBe(401);
  }
});

test("registration returns to analysis and a member can submit an actual PDF", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await page.getByLabel("이름", { exact: true }).fill("새 커리어 회원");
  await page
    .getByLabel("이메일", { exact: true })
    .fill(`resume-member-${randomUUID()}@example.com`);
  await page.getByLabel("비밀번호", { exact: true }).fill("Career-test-2026!");
  await page
    .getByRole("button", { name: "가입하고 분석 시작하기", exact: true })
    .click();
  await expect(page).toHaveURL(/\/analysis$/);
  await expect(page.getByLabel("PDF 이력서 추가")).toBeEnabled();
  await page
    .getByLabel("PDF 이력서 추가")
    .setInputFiles("public/downloads/career-resume-template.pdf");
  await page
    .getByRole("button", { name: "분석 시작하기", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "분석 완료", exact: true }),
  ).toBeVisible();
});

test("expired membership is rechecked before any selected source is sent", async ({
  page,
}) => {
  let member = true;
  let submissions = 0;
  await page.route("**/api/account", (route) =>
    route.fulfill({
      json: member
        ? { user: { id: "member" }, guest: false }
        : { user: null, guest: false },
    }),
  );
  await page.route("**/api/analyze", (route) => {
    submissions++;
    return route.fulfill({ json: { workspace: {} } });
  });
  await page.goto("/analysis");
  await expect(page.getByLabel("공개 GitHub 저장소 URL")).toBeEnabled();
  await page
    .getByLabel("공개 GitHub 저장소 URL")
    .fill("https://github.com/example/project");
  await page.getByRole("button", { name: "링크 추가", exact: true }).click();
  member = false;
  await page
    .getByRole("button", { name: "분석 시작하기", exact: true })
    .click();
  await expect(page.locator(".analysis-error")).toContainText("로그인 후");
  expect(submissions).toBe(0);
});

test("Word template is readable and contains the resume sections", async () => {
  const mammoth = await import("mammoth");
  const result = await mammoth.extractRawText({
    buffer: readFileSync("public/downloads/career-resume-template.docx"),
  });
  for (const section of [
    "이미지 삽입",
    "성명",
    "연락처",
    "이메일",
    "프로젝트 경험",
    "학력",
    "자격증",
    "직접 수행한 작업",
  ])
    expect(result.value).toContain(section);
});
