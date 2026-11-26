import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { loadEnvConfig } from "@next/env";
import { Client } from "pg";

test("publication admin authorization and hide/restore UI", async ({
  page,
  playwright,
}) => {
  test.skip(
    process.env.RUN_RDS_PUBLICATION_TESTS !== "1",
    "Explicit account-RDS integration opt-in",
  );
  test.setTimeout(120000);
  loadEnvConfig(process.cwd(), true, { info() {}, error() {} });
  const namespace = process.env.CAREER_PROFILE_NAMESPACE || "local-review";
  const db = new Client({
    connectionString: process.env.CAREER_PROFILE_DATABASE_URL,
    ssl: process.env.CAREER_PROFILE_CA_FILE
      ? {
          ca: readFileSync(process.env.CAREER_PROFILE_CA_FILE, "utf8"),
          rejectUnauthorized: true,
        }
      : undefined,
  });
  const headers = { origin: "http://127.0.0.1:3000" };
  const anon = await playwright.request.newContext({ baseURL: headers.origin });
  let subject: string | undefined;
  await db.connect();
  try {
    expect((await anon.get("/api/admin/postings")).status()).toBe(401);
    expect(
      (await anon.patch("/api/admin/postings", { headers, data: {} })).status(),
    ).toBe(401);
    const registration = await page.request.post("/api/account", {
      headers,
      data: {
        action: "register",
        email: `publication-${randomUUID()}@example.test`,
        password: randomUUID(),
        name: "노출 관리 검증",
      },
    });
    expect(registration.status()).toBe(200);
    subject = (await registration.json()).user.id;
    expect((await page.request.get("/api/admin/postings")).status()).toBe(403);
    expect(
      (
        await page.request.patch("/api/admin/postings", { headers, data: {} })
      ).status(),
    ).toBe(403);
    await db.query(
      "INSERT INTO public.career_lv_member(namespace,subject_id,app_role) VALUES($1,$2,'ADMIN') ON CONFLICT(namespace,subject_id) DO UPDATE SET app_role='ADMIN'",
      [namespace, subject],
    );
    const actual = await page.request.get("/api/admin/postings");
    expect(actual.status()).toBe(200);
    const live = await actual.json();
    expect(live.total).toBeGreaterThan(20);
    expect(live.items).toHaveLength(20);
    expect(
      (
        await page.request.patch("/api/admin/postings", {
          headers: { origin: "https://invalid.example" },
          data: {},
        })
      ).status(),
    ).toBe(403);
    expect(
      (
        await page.request.patch("/api/admin/postings", {
          headers,
          data: { id: "1", hidden: "yes", revision: 0 },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await page.request.patch("/api/admin/postings", {
          headers,
          data: { id: "9007199254740990", hidden: true, revision: 0 },
        })
      ).status(),
    ).toBe(409);
    await page.goto("/admin?tab=postings");
    await expect(page.locator(".publication-row")).toHaveCount(20);
    await expect(
      page.getByRole("navigation", { name: "공고 노출 관리 페이지" }),
    ).toContainText(`1 / ${Math.ceil(live.total / 20)} 페이지`);
    await page.screenshot({
      path: "work/publication-live-desktop.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "work/publication-live-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    const items = [
      {
        id: "1001",
        company: "검증 회사",
        title: "백엔드 개발자",
        site: "사람인",
        postingNo: "55500001",
        deadline: null,
        hidden: false,
        revision: 0,
        eligible: true,
        state: "PUBLISHED",
        sourceUrl: "",
      },
      {
        id: "1002",
        company: "검증 회사",
        title: "마감 후 숨긴 공고",
        site: "사람인",
        postingNo: "55500002",
        deadline: "2020-01-01",
        hidden: true,
        revision: 1,
        eligible: false,
        state: "HIDDEN",
        sourceUrl: "",
      },
    ];
    let fail = false;
    await page.route("**/api/admin/postings**", async (route) => {
      const req = route.request();
      if (req.method() === "PATCH") {
        const input = req.postDataJSON();
        const item = items.find((i) => i.id === input.id)!;
        item.hidden = input.hidden;
        item.revision++;
        item.state = input.hidden ? "HIDDEN" : "PUBLISHED";
        await route.fulfill({ json: { ok: true } });
        return;
      }
      if (fail) {
        await route.fulfill({ status: 503, json: { error: "연결 오류" } });
        return;
      }
      const status =
        new URL(req.url()).searchParams.get("status") || "PUBLISHED";
      const list = items.filter((i) => i.state === status);
      await route.fulfill({
        json: {
          total: list.length,
          items: list,
          counts: {
            PUBLISHED: items.filter((i) => !i.hidden).length,
            HIDDEN: items.filter((i) => i.hidden).length,
          },
        },
      });
    });
    await page.reload();
    await page.getByRole("button", { name: "숨기기", exact: true }).click();
    await expect(page.locator(".review-success")).toContainText(
      "공고를 숨겼습니다",
    );
    await expect(page.locator(".publication-row")).toHaveCount(0);
    await page.getByRole("button", { name: /^숨긴 공고/ }).click();
    await expect(page.locator(".publication-row")).toHaveCount(2);
    await expect(
      page
        .locator(".publication-row")
        .filter({ hasText: "마감 후 숨긴 공고" })
        .getByRole("button", { name: "다시 올리기" }),
    ).toBeDisabled();
    await page
      .locator(".publication-row")
      .filter({ hasText: "백엔드 개발자" })
      .getByRole("button", { name: "다시 올리기" })
      .click();
    await expect(page.locator(".review-success")).toContainText(
      "공고를 다시 올렸습니다",
    );
    await page.getByRole("button", { name: /^노출 중/ }).click();
    await expect(page.locator(".publication-row")).toHaveCount(1);
    fail = true;
    await page.reload();
    await expect(
      page.locator(".extraction-review").getByRole("alert"),
    ).toContainText("연결 오류");
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
    await anon.dispose();
    await db.end();
  }
});
