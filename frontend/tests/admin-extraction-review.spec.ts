import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { loadEnvConfig } from "@next/env";
import { Client } from "pg";

test("admin review enforces permissions and persists pass, feedback, audit and concurrency", async ({
  page,
  playwright,
}) => {
  test.skip(
    process.env.RUN_RDS_ADMIN_REVIEW_TESTS !== "1",
    "Explicit RDS integration opt-in",
  );
  test.setTimeout(90000);
  loadEnvConfig(process.cwd(), false, { info() {}, error() {} });
  const base = "http://127.0.0.1:3000",
    namespace =
      process.env.CAREER_PIPELINE_NAMESPACE ||
      process.env.CAREER_PROFILE_NAMESPACE ||
      "local-review";
  const marker = randomUUID(),
    email = `review-${marker}@example.test`;
  const db = new Client({
    connectionString: process.env.CAREER_PROFILE_DATABASE_URL,
    ssl: {
      ca: readFileSync(process.env.CAREER_PROFILE_CA_FILE!, "utf8"),
      rejectUnauthorized: true,
    },
    connectionTimeoutMillis: 5000,
  });
  const anon = await playwright.request.newContext({ baseURL: base });
  const headers = { origin: base };
  const ids: string[] = [];
  let subject: string | undefined;
  await db.connect();
  try {
    expect((await anon.get("/api/admin/extraction-reviews")).status()).toBe(
      401,
    );
    expect(
      (
        await anon.patch("/api/admin/extraction-reviews", { headers, data: {} })
      ).status(),
    ).toBe(401);
    const registered = await page.request.post(base + "/api/account", {
      headers,
      data: {
        action: "register",
        email,
        password: randomUUID(),
        name: "관리자 UI 검증",
      },
    });
    expect(registered.status()).toBe(200);
    subject = (await registered.json()).user.id;
    expect(
      (await page.request.get(base + "/api/admin/extraction-reviews")).status(),
    ).toBe(403);
    await page.goto("/admin");
    await expect(
      page.getByRole("heading", { name: "페이지가 없어요.", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".review-toolbar")).toHaveCount(0);
    await db.query(
      "INSERT INTO public.career_lv_member(namespace,subject_id,app_role) VALUES($1,$2,'ADMIN')",
      [process.env.CAREER_PROFILE_NAMESPACE || "local-review", subject],
    );
    for (const [suffix, ns] of [
      ["one", namespace],
      ["race", namespace],
      ["other", namespace + "-test-other"],
      ["missing", namespace],
    ]) {
      const row = await db.query(
        "INSERT INTO public.career_extraction_review(namespace,site,posting_no,company,title,stage,error_code,failure_count,last_failed_at) VALUES($1,'TEST',$2,'검증 기업',$3,$4,'응답 형식 오류',2,now()) RETURNING id::text",
        [
          ns,
          marker + suffix,
          "예시 추출 오류 " + suffix,
          suffix === "missing" ? "UNKNOWN" : "REVIEW",
        ],
      );
      ids.push(row.rows[0].id);
    }
    const api = base + "/api/admin/extraction-reviews";
    const filtered = await (
      await page.request.get(api + "?q=" + marker)
    ).json();
    expect(filtered.items).toHaveLength(2);
    expect(
      filtered.items.every(
        (item: { stage: string }) => item.stage === "REVIEW",
      ),
    ).toBe(true);
    expect(
      (
        await page.request.patch(api, {
          headers: { origin: "https://invalid.example" },
          data: { id: ids[0], revision: 0, action: "PASS" },
        })
      ).status(),
    ).toBe(403);
    expect(
      (
        await page.request.patch(api, {
          headers,
          data: { id: ids[0], revision: 0, action: "RETRY", feedback: " " },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await page.request.patch(api, {
          headers,
          data: { id: ids[2], revision: 0, action: "PASS" },
        })
      ).status(),
    ).toBe(404);
    await page.goto("/admin");
    await expect(
      page.getByRole("heading", { name: "관리자", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "관리자", exact: true }),
    ).toBeVisible();
    const row = page.locator(".review-row").filter({
      has: page.getByRole("heading", {
        name: "예시 추출 오류 one",
        exact: true,
      }),
    });
    await expect(row).toBeVisible();
    await expect(
      row.getByText("자동 재시도 보류", { exact: true }),
    ).toBeVisible();
    await row
      .getByRole("button", { name: "넘기기 (PASS)", exact: true })
      .click();
    await expect(page.locator(".review-success")).toContainText(
      "공고를 넘겼습니다",
    );
    expect(
      (
        await db.query(
          "SELECT status FROM public.career_extraction_review WHERE id=$1",
          [ids[0]],
        )
      ).rows[0].status,
    ).toBe("SKIPPED");
    expect(
      (
        await page.request.patch(api, {
          headers,
          data: { id: ids[0], revision: 0, action: "PASS" },
        })
      ).status(),
    ).toBe(409);
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("SKIPPED");
    await row
      .getByRole("button", { name: "재추출 피드백", exact: true })
      .click();
    const feedback =
      "자격요건 하단의 표를 다시 확인하고 누락된 API 설계 문장을 포함해 주세요.";
    await page.getByLabel("역량 재추출 피드백", { exact: true }).fill(feedback);
    await page
      .getByRole("button", { name: "피드백 저장 및 재추출 요청", exact: true })
      .click();
    await expect(page.locator(".review-success")).toContainText(
      "재추출 요청을 저장했습니다",
    );
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("RETRY_REQUESTED");
    await expect(row.locator(".review-saved-feedback")).toContainText(feedback);
    const stored = await db.query(
      "SELECT status,feedback FROM public.career_extraction_review WHERE id=$1",
      [ids[0]],
    );
    expect(stored.rows[0]).toEqual({ status: "RETRY_REQUESTED", feedback });
    expect(
      (
        await db.query(
          "SELECT action FROM public.career_extraction_review_event WHERE review_id=$1 ORDER BY created_at,id",
          [ids[0]],
        )
      ).rows.map((r) => r.action),
    ).toEqual(["PASS", "RETRY"]);
    const race = await Promise.all([
      page.request.patch(api, {
        headers,
        data: { id: ids[1], revision: 0, action: "PASS" },
      }),
      page.request.patch(api, {
        headers,
        data: {
          id: ids[1],
          revision: 0,
          action: "RETRY",
          feedback: "본문 하단을 확인하세요",
        },
      }),
    ]);
    expect(race.map((r) => r.status()).sort()).toEqual([200, 409]);
    await page
      .getByRole("link", { name: "공지사항 관리", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "공지 작성", exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: "추출 검토", exact: true }).click();
    await expect(page.locator(".review-toolbar")).toBeVisible();
    await page.screenshot({
      path: "work/admin-extraction-review-desktop.png",
      fullPage: true,
    });
    for (const width of [1024, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await page.screenshot({
      path: "work/admin-extraction-review-mobile.png",
      fullPage: true,
    });
    await page.route("**/api/admin/extraction-reviews?**", (route) =>
      route.fulfill({ status: 503, json: { error: "검토 목록 연결 실패" } }),
    );
    await page.reload();
    await expect(
      page.locator(".extraction-review").getByRole("alert"),
    ).toContainText("검토 목록 연결 실패");
    await expect(
      page.getByRole("heading", { name: "해당 공고가 없습니다", exact: true }),
    ).toHaveCount(0);
  } finally {
    await db.query(
      "DELETE FROM public.career_extraction_review WHERE id=ANY($1::bigint[])",
      [ids],
    );
    if (subject) {
      await db.query(
        "DELETE FROM public.career_lv_member WHERE namespace=$1 AND subject_id=$2",
        [process.env.CAREER_PROFILE_NAMESPACE || "local-review", subject],
      );
      await db.query(
        "DELETE FROM public.career_account WHERE namespace=$1 AND subject_id=$2",
        [process.env.CAREER_PROFILE_NAMESPACE || "local-review", subject],
      );
      const local = new DatabaseSync(
        path.join(
          process.env.CAREER_DATA_DIR || ".career-data",
          "career.sqlite",
        ),
      );
      for (const table of ["sessions", "profiles", "workspaces"])
        local.prepare(`DELETE FROM ${table} WHERE user_id=?`).run(subject);
      local.prepare("DELETE FROM users WHERE id=?").run(subject);
      local.close();
    }
    await db.end();
    await anon.dispose();
  }
});
