import { test, expect } from "@playwright/test";
import { randomUUID, randomBytes, createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import path from "node:path";
import { Client } from "pg";
import AxeBuilder from "@axe-core/playwright";

test("notice permissions, one-time admin setup and GitHub preview persist in RDS", async ({
  page,
  playwright,
}) => {
  test.skip(
    process.env.RUN_RDS_COMMUNITY_TESTS !== "1",
    "Explicit local RDS integration opt-in",
  );
  test.setTimeout(120000);
  const base = "http://127.0.0.1:3000",
    email = `community-${randomUUID()}@example.test`,
    password = randomUUID();
  const anonymous = await playwright.request.newContext({ baseURL: base });
  expect((await anonymous.get("/api/notices")).status()).toBe(200);
  expect(
    (
      await anonymous.post("/api/notices", {
        headers: { origin: base },
        data: { title: "No", content: "No" },
      })
    ).status(),
  ).toBe(401);
  const registered = await page.request.post("/api/account", {
    headers: { origin: base },
    data: { action: "register", email, password, name: "권한 검증" },
  });
  expect(registered.ok()).toBe(true);
  const subject = (await registered.json()).user.id as string;
  const env = Object.fromEntries(
    readFileSync(".env.local", "utf8")
      .split(/\r?\n/)
      .filter((line) => line.includes("=") && !line.startsWith("#"))
      .map((line) => {
        const i = line.indexOf("=");
        return [line.slice(0, i), line.slice(i + 1)];
      }),
  );
  const namespace = env.CAREER_PROFILE_NAMESPACE || "local-review";
  const connection = new Client({
    connectionString: env.CAREER_PROFILE_DATABASE_URL,
    ssl: {
      ca: readFileSync(env.CAREER_PROFILE_CA_FILE, "utf8"),
      rejectUnauthorized: true,
    },
  });
  await connection.connect();
  try {
    expect(
      (
        await page.request.post("/api/notices", {
          headers: { origin: base },
          data: {
            title: "No",
            content: "No",
            role: "ADMIN",
            userId: "career-system",
          },
        })
      ).status(),
    ).toBe(403);
    let liveAnalysis = 0;
    await page.route("**/api/analyze", (route) => {
      liveAnalysis++;
      return route.fulfill({
        status: 500,
        json: { error: "Live API must not be used" },
      });
    });
    await page.goto("/analysis");
    await page
      .getByRole("button", { name: "예시 링크 사용", exact: true })
      .click();
    await expect(page.getByLabel("공개 GitHub 저장소 URL")).toHaveValue(
      "https://github.com/career-demo/order-service",
    );
    await page.getByRole("button", { name: "링크 추가", exact: true }).click();
    await page
      .getByRole("button", { name: "분석 시작하기", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "분석 완료", exact: true }),
    ).toBeVisible();
    expect(liveAnalysis).toBe(0);
    const workspace = await (await page.request.get("/api/career")).json();
    expect(workspace.workspace.runs[0].simulated).toBe(true);
    await page.goto("/jobs?job=study-demo-backend&demo=low&view=stats");
    await expect(page.getByTestId("saved-level-radar")).toBeVisible();
    await expect(page.locator(".personal-job-comparison")).not.toContainText(
      "분석 자료 2개",
    );
    await expect(page.locator(".personal-job-comparison")).not.toContainText(
      "GitHub·PDF 등록을 가정한 더미 평가",
    );
    const ownRole = await connection.query(
      "SELECT app_role FROM public.career_lv_member WHERE namespace=$1 AND subject_id=$2",
      [namespace, subject],
    );
    expect(ownRole.rows[0].app_role).toBe("MEMBER");
    await connection.query(
      "UPDATE public.career_lv_member SET app_role='ADMIN' WHERE namespace=$1 AND subject_id=$2",
      [namespace, subject],
    );
    const token = randomBytes(32).toString("hex"),
      local = new DatabaseSync(path.resolve(".career-data/career.sqlite"));
    local
      .prepare("INSERT INTO admin_invitations VALUES(?,?,?,NULL)")
      .run(
        createHash("sha256").update(token).digest("hex"),
        subject,
        Date.now() + 60000,
      );
    local.close();
    const nextPassword = randomUUID();
    await page.goto(`/admin/setup#token=${token}`);
    await page.getByLabel("비밀번호", { exact: true }).fill(nextPassword);
    await page.getByLabel("비밀번호 확인", { exact: true }).fill(nextPassword);
    await page
      .getByRole("button", { name: "설정하고 로그인", exact: true })
      .click();
    await expect(page).toHaveURL(/\/notices$/);
    expect(
      (
        await page.request.post("/api/admin/activate", {
          headers: { origin: base },
          data: { token, password: nextPassword },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await page.request.post("/api/notices", {
          headers: { origin: "https://invalid.example" },
          data: { title: "No", content: "No" },
        })
      ).status(),
    ).toBe(403);
    await page.goto("/notices");
    await page.getByRole("button", { name: "공지 작성", exact: true }).click();
    const title = `검증 공지 ${randomUUID()}`;
    await page.getByLabel("제목", { exact: true }).fill(title);
    await page
      .getByLabel("내용", { exact: true })
      .fill("줄바꿈을 보존합니다.\n<script>window.__noticeXss=true</script>");
    await page.getByRole("button", { name: "저장", exact: true }).click();
    await page.getByRole("button", { name: new RegExp(title) }).click();
    await expect(page.locator(".notice-content")).toContainText("<script>");
    expect(
      await page.evaluate(() => Object.hasOwn(window, "__noticeXss")),
    ).toBe(false);
    await page.getByRole("button", { name: "수정", exact: true }).click();
    await page.getByLabel("제목", { exact: true }).fill(title + " 수정");
    await page.getByRole("button", { name: "저장", exact: true }).click();
    await page.reload();
    await page
      .getByRole("button", { name: new RegExp(title + " 수정") })
      .click();
    await page.getByRole("button", { name: "삭제", exact: true }).click();
    await page.getByRole("button", { name: "삭제 확인", exact: true }).click();
    await expect(
      page.getByRole("button", { name: new RegExp(title) }),
    ).toHaveCount(0);
    await connection.query(
      "UPDATE public.career_lv_member SET app_role='MEMBER' WHERE namespace=$1 AND subject_id=$2",
      [namespace, subject],
    );
    expect(
      (
        await page.request.post("/api/notices", {
          headers: { origin: base },
          data: { title: "No", content: "No" },
        })
      ).status(),
    ).toBe(403);
    await page.reload();
    await expect(
      page.getByRole("button", { name: "공지 작성", exact: true }),
    ).toHaveCount(0);
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
  } finally {
    await connection.query(
      "DELETE FROM public.career_notice WHERE namespace=$1 AND author_id=$2",
      [namespace, subject],
    );
    await connection.query(
      "DELETE FROM public.career_lv_member WHERE namespace=$1 AND subject_id=$2",
      [namespace, subject],
    );
    await connection.end();
    await anonymous.dispose();
  }
});

test("unconfigured Kakao login and invalid OAuth state fail safely", async ({
  page,
}) => {
  await page.goto("/sign-in");
  const status = await (
    await page.request.get("/api/auth/kakao/status")
  ).json();
  if (!status.configured) {
    await expect(
      page.getByRole("button", { name: "카카오로 시작하기", exact: true }),
    ).toBeDisabled();
    expect((await page.request.get("/api/auth/kakao")).status()).toBe(503);
  }
  const response = await page.request.get(
    "/api/auth/kakao/callback?code=invalid&state=invalid",
    { maxRedirects: 0 },
  );
  expect(response.status()).toBe(303);
  expect(response.headers().location).toContain("error=kakao_state");
  await page.context().addCookies([
    {
      name: "career_kakao_state",
      value: "a".repeat(64),
      domain: "127.0.0.1",
      path: "/api/auth/kakao",
    },
  ]);
  const invalid = await page.request.get(
    "/api/auth/kakao/callback?code=invalid&state=" +
      encodeURIComponent("가".repeat(64)),
    { maxRedirects: 0 },
  );
  expect(invalid.status()).toBe(303);
});
