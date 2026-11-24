import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { loadEnvConfig } from "@next/env";
import { Client } from "pg";

test("admin permissions and review UI use extraction-run decisions without mutating live postings", async ({
  page,
  playwright,
}) => {
  test.skip(
    process.env.RUN_RDS_ADMIN_REVIEW_TESTS !== "1",
    "Explicit account-RDS integration opt-in",
  );
  loadEnvConfig(process.cwd(), false, { info() {}, error() {} });
  const base = "http://127.0.0.1:3000";
  const namespace = process.env.CAREER_PROFILE_NAMESPACE || "local-review";
  const headers = { origin: base };
  const db = new Client({
    connectionString: process.env.CAREER_PROFILE_DATABASE_URL,
    ssl: {
      ca: readFileSync(process.env.CAREER_PROFILE_CA_FILE!, "utf8"),
      rejectUnauthorized: true,
    },
  });
  const anon = await playwright.request.newContext({ baseURL: base });
  let subject: string | undefined;
  await db.connect();
  try {
    expect((await anon.get("/api/admin/closed-postings")).status()).toBe(401);
    expect((await anon.get("/api/admin/extraction-reviews")).status()).toBe(
      401,
    );
    expect(
      (
        await anon.patch("/api/admin/extraction-reviews", { headers, data: {} })
      ).status(),
    ).toBe(401);
    const registration = await page.request.post("/api/account", {
      headers,
      data: {
        action: "register",
        email: `review-${randomUUID()}@example.test`,
        password: randomUUID(),
        name: "관리자 검증",
      },
    });
    expect(registration.status()).toBe(200);
    subject = (await registration.json()).user.id;
    expect(
      (await page.request.get("/api/admin/closed-postings")).status(),
    ).toBe(403);
    expect(
      (await page.request.get("/api/admin/extraction-reviews")).status(),
    ).toBe(403);
    expect(
      (
        await page.request.patch("/api/admin/extraction-reviews", {
          headers,
          data: {},
        })
      ).status(),
    ).toBe(403);
    await db.query(
      "INSERT INTO public.career_lv_member(namespace,subject_id,app_role) VALUES($1,$2,'ADMIN')",
      [namespace, subject],
    );
    const live = await page.request.get("/api/admin/extraction-reviews");
    const closed = await page.request.get("/api/admin/closed-postings");
    expect(closed.status()).toBe(200);
    const closedData = await closed.json();
    expect(closedData.total).toBeGreaterThan(0);
    await page.goto("/admin?tab=closed");
    await expect(
      page.getByRole("heading", { name: "마감 공고", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".closed-postings-list article")).toHaveCount(
      Math.min(20, closedData.total),
    );
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `work/closed-postings-${width}.png`,
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    expect(live.status()).toBe(200);
    expect((await live.json()).storage).toBe("extraction_run");
    expect(
      (
        await page.request.patch("/api/admin/extraction-reviews", {
          headers: { origin: "https://invalid.example" },
          data: {},
        })
      ).status(),
    ).toBe(403);
    expect(
      (
        await page.request.patch("/api/admin/extraction-reviews", {
          headers,
          data: {
            id: "0",
            revision: "a".repeat(32),
            action: "RETRY",
            feedback: "　 \n",
          },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await page.request.patch("/api/admin/extraction-reviews", {
          headers,
          data: { id: "0", revision: "a".repeat(32), action: "PASS" },
        })
      ).status(),
    ).toBe(404);
    const items = ["1001", "1002"].map((id, index) => ({
      id,
      postingNo: String(55000000 + index),
      site: "사람인",
      company: "검증 기업",
      title: `검토 공고 ${index + 1}`,
      sourceUrl: "",
      status: "OPEN",
      deadlinePassed: false,
      feedback: "",
      updatedAt: new Date().toISOString(),
      revision: "a".repeat(32),
      reviewReasons: [
        { 검사: 2, 내용: "모집 직무 칸 3개 / 만든 자리 이름 1개" },
      ],
    }));
    await page.route("**/api/admin/extraction-reviews**", async (route) => {
      const request = route.request();
      if (request.method() === "POST") {
        expect(request.postDataJSON().action).toBe("PASS_EXPIRED");
        const expired = items.filter(
          (item) => item.status === "OPEN" && item.deadlinePassed,
        );
        expired.forEach((item) => {
          item.status = "SKIPPED";
          item.feedback = "마감일 경과로 넘김";
        });
        await route.fulfill({ json: { ok: true, updated: expired.length } });
      } else if (request.method() === "PATCH") {
        const body = request.postDataJSON();
        expect(body.revision).toMatch(/^[a-f0-9]{32}$/);
        const item = items.find((item) => item.id === body.id)!;
        item.status = (
          {
            PASS: "SKIPPED",
            RETRY: "RETRY_REQUESTED",
            APPROVE: "RESOLVED",
            RESTORE: "OPEN",
          } as Record<string, string>
        )[body.action];
        item.feedback = body.feedback;
        await route.fulfill({ json: { ok: true, status: item.status } });
      } else {
        const params = new URL(request.url()).searchParams;
        const status = params.get("status");
        const visible = items.filter(
          (item) => status === "ALL" || item.status === status,
        );
        await route.fulfill({
          json: {
            storage: "extraction_run",
            items: visible,
            total: visible.length,
            nextOffset: null,
            lastPipelineAt: null,
            expiredOpenCount: items.filter(
              (item) => item.status === "OPEN" && item.deadlinePassed,
            ).length,
            counts: Object.fromEntries(
              ["OPEN", "SKIPPED", "RETRY_REQUESTED", "RESOLVED"].map(
                (status) => [
                  status,
                  items.filter((item) => item.status === status).length,
                ],
              ),
            ),
          },
        });
      }
    });
    await page.goto("/admin");
    await expect(page.locator(".review-row")).toHaveCount(2);
    await expect(page.locator(".review-reasons").first()).toContainText(
      "모집 직무 구분 확인 필요",
    );
    await expect(
      page.getByRole("option", { name: "처리 중", exact: true }),
    ).toHaveCount(0);
    await page
      .locator(".review-row")
      .first()
      .getByRole("button", { name: "넘기기 (PASS)", exact: true })
      .click();
    await expect(page.locator(".review-success")).toContainText("제외로 저장");
    await expect(page.locator(".review-row")).toHaveCount(1);
    await page.getByRole("link", { name: "넘긴 공고", exact: true }).click();
    await expect(page).toHaveURL(/tab=skipped/);
    await expect(
      page
        .locator(".review-row")
        .getByRole("button", { name: "재추출 피드백", exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "검토 대기로 되돌리기", exact: true })
      .click();
    await expect(page.locator(".review-row")).toHaveCount(0);
    await page.getByRole("link", { name: "추출 검토", exact: true }).click();
    await expect(page.locator(".review-row")).toHaveCount(2);
    await page
      .locator(".review-row")
      .first()
      .getByRole("button", { name: "정상 등록", exact: true })
      .click();
    await expect(page.locator(".review-success")).toContainText(
      "정상으로 등록",
    );
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("RESOLVED");
    await expect(page.locator(".review-row")).toHaveCount(1);
    await page
      .getByRole("button", { name: "검토 대기로 되돌리기", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("OPEN");
    await page
      .locator(".review-row")
      .first()
      .getByRole("button", { name: "넘기기 (PASS)", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("OPEN");
    await page
      .locator(".review-row")
      .getByRole("button", { name: "재추출 피드백", exact: true })
      .click();
    await page
      .getByLabel("역량 재추출 피드백", { exact: true })
      .fill("직무 이름 중복을 확인해 주세요");
    await page
      .getByRole("button", { name: "피드백 저장 및 재추출 요청", exact: true })
      .click();
    await expect(page.locator(".review-success")).toContainText(
      "재추출 요청을 저장",
    );
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("RETRY_REQUESTED");
    await expect(page.locator(".review-saved-feedback")).toContainText(
      "직무 이름 중복을 확인해 주세요",
    );
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    items.push({
      ...items[0],
      id: "1003",
      status: "OPEN",
      deadlinePassed: true,
      feedback: "",
    });
    await page.reload();
    await expect(
      page.getByRole("button", { name: "정상 등록", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "재추출 피드백", exact: true }),
    ).toBeDisabled();
    await page
      .getByRole("button", {
        name: "마감일 지난 공고 넘기기 (1개)",
        exact: true,
      })
      .click();
    await expect(page.locator(".review-success")).toContainText(
      "1개 공고를 넘김 처리",
    );
    await page.getByRole("link", { name: "넘긴 공고", exact: true }).click();
    await expect(page.locator(".review-row")).toHaveCount(2);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({
      path: "work/admin-skipped-restore-desktop.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.screenshot({
      path: "work/admin-skipped-restore-mobile.png",
      fullPage: true,
    });
    await page.route("**/api/admin/extraction-reviews**", (route) =>
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
    if (subject) {
      await db.query(
        "DELETE FROM public.career_lv_member WHERE namespace=$1 AND subject_id=$2",
        [namespace, subject],
      );
      await db.query(
        "DELETE FROM public.career_account WHERE namespace=$1 AND subject_id=$2",
        [namespace, subject],
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
