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
  test.setTimeout(120000);
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
    expect((await anon.get("/api/admin/extraction-reviews/1")).status()).toBe(
      401,
    );
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
      (await page.request.get("/api/admin/extraction-reviews/1")).status(),
    ).toBe(403);
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
    expect(
      (
        await page.request.get("/api/admin/extraction-reviews/not-an-id")
      ).status(),
    ).toBe(400);
    expect(
      (
        await page.request.get(
          "/api/admin/extraction-reviews/9223372036854775808",
        )
      ).status(),
    ).toBe(400);
    expect(
      (
        await page.request.get("/api/admin/extraction-reviews/9007199254740990")
      ).status(),
    ).toBe(404);
    const realItem = (await live.json()).items[0];
    if (realItem) {
      const realDetail = await page.request.get(
        `/api/admin/extraction-reviews/${realItem.id}`,
      );
      expect(realDetail.status()).toBe(200);
      expect((await realDetail.json()).review.id).toBe(realItem.id);
      await page.goto("/admin");
      await expect(
        page
          .locator(".review-row")
          .first()
          .locator("h2 a.review-detail-trigger"),
      ).toBeVisible();
      await expect(
        page.locator(".review-row").first().locator("h2 button"),
      ).toHaveCount(0);
      await page
        .locator(".review-row")
        .first()
        .screenshot({ path: "work/review-list-inline-title.png" });
      await page
        .getByRole("button", { name: "원문과 LLM 결과 비교", exact: true })
        .first()
        .click();
      await expect(
        page
          .getByRole("region", { name: "공고 추출 비교" })
          .getByRole("heading", { name: "LLM 추출 결과", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("navigation", { name: "관리자 하위 메뉴" }),
      ).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.screenshot({
        path: "work/review-source-llm-live.png",
        fullPage: true,
      });
      await page.getByRole("button", { name: "뒤로가기", exact: true }).click();
    }
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
    let staleDetail = false,
      modalDecision = false;
    await page.route("**/api/admin/extraction-reviews**", async (route) => {
      const request = route.request();
      const match = new URL(request.url()).pathname.match(
        /\/extraction-reviews\/(\d+)$/,
      );
      if (request.method() === "GET" && match) {
        const item = items.find((row) => row.id === match[1])!;
        await route.fulfill({
          json: {
            review: { ...item, revision: "b".repeat(32) },
            posting: {
              id: "321",
              bodyHtml:
                item.id === "1001"
                  ? '<h2>모집 직무 원문</h2><p>원문 근거 문장</p><script>parent.__reviewXss=1</script><iframe src="https://invalid.example"></iframe><img src="javascript:alert(1)" onerror="parent.__reviewXss=1"><a href="javascript:alert(1)">링크 글자</a>'
                  : null,
              lastCheckedAt: new Date().toISOString(),
              images: [],
            },
            extraction: {
              id: item.id,
              isCurrent: !staleDetail,
              model: "stored-model",
              promptVersion: "p1",
              dictVersion: "d1",
              runAt: new Date().toISOString(),
              rawOutput:
                item.id === "1001"
                  ? {
                      positions: [
                        {
                          name: "LLM 원본 직무",
                          job: "백엔드",
                          it_job: true,
                          career: "경력",
                          years: "3년 이상",
                          required: [
                            {
                              text: "LLM이 추출한 요건",
                              quote: "원문 근거 문장",
                              reqs: [],
                            },
                          ],
                          preferred: [],
                          duties: [],
                          other: [],
                        },
                      ],
                      skipped: ["추출 제외 내용"],
                      notes: "응답 메모",
                    }
                  : null,
              units: [
                {
                  id: "1",
                  name: "DB 저장 직무",
                  isIt: true,
                  job: "백엔드",
                  career: "경력",
                  years: "3년",
                  items: [
                    {
                      category: "필수",
                      text: "DB 정규화 문장",
                      quote: "원문 근거 문장",
                    },
                  ],
                },
              ],
            },
          },
        });
        return;
      }
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
        if (modalDecision) {
          expect(body.revision).toBe("b".repeat(32));
          modalDecision = false;
        }
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
    await page
      .getByRole("textbox", { name: "공고 검색", exact: true })
      .fill("검토 공고");
    await page.getByRole("button", { name: "검색", exact: true }).click();
    await expect(page.locator(".review-row")).toHaveCount(2);
    await page.evaluate(() => window.scrollTo(0, 400));
    const listScroll = await page.evaluate(() => window.scrollY);
    await page
      .getByRole("button", { name: "원문과 LLM 결과 비교", exact: true })
      .first()
      .click();
    const dialog = page.getByRole("region", { name: "공고 추출 비교" });
    await expect(
      page.getByRole("navigation", { name: "관리자 하위 메뉴" }),
    ).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator(".review-list")).toHaveCount(0);
    await expect(
      dialog.getByRole("heading", { name: "LLM 원본 직무", exact: true }),
    ).toBeVisible();
    await expect(
      page
        .frameLocator('iframe[title="저장된 공고 원문"]')
        .getByText("원문 근거 문장"),
    ).toBeVisible();
    expect(
      await page
        .frameLocator('iframe[title="저장된 공고 원문"]')
        .locator("script,iframe,a,[onerror]")
        .count(),
    ).toBe(0);
    expect(
      await page.evaluate(() => Object.hasOwn(window, "__reviewXss")),
    ).toBe(false);
    await dialog
      .getByRole("button", { name: "JSON 원본", exact: true })
      .click();
    await expect(dialog.locator("pre")).toContainText("LLM이 추출한 요건");
    await dialog
      .getByRole("button", { name: "DB 저장 결과", exact: true })
      .click();
    await expect(
      dialog.getByText("DB 정규화 문장", { exact: true }),
    ).toBeVisible();
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(
        await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole("button", { name: "뒤로가기", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(
      page.getByRole("textbox", { name: "공고 검색", exact: true }),
    ).toHaveValue("검토 공고");
    await expect
      .poll(() => page.evaluate(() => Math.round(window.scrollY)))
      .toBe(Math.round(listScroll));
    staleDetail = true;
    await page
      .getByRole("button", { name: "원문과 LLM 결과 비교", exact: true })
      .nth(1)
      .click();
    await expect(
      dialog.getByText(
        "새 추출 결과가 저장되어 이 실행은 현재 결과가 아닙니다.",
        { exact: false },
      ),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "검토 대기로 되돌리기", exact: true }),
    ).toBeDisabled();
    await expect(
      dialog.getByText("LLM 원본이 저장되지 않았거나 구조화 형식이 아닙니다.", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(
      dialog.getByText("저장된 원문과 이미지가 없습니다.", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "뒤로가기", exact: true }).click();
    staleDetail = false;
    await page
      .getByRole("button", { name: "원문과 LLM 결과 비교", exact: true })
      .first()
      .click();
    await dialog
      .getByRole("button", { name: "재추출 피드백", exact: true })
      .click();
    await dialog
      .getByRole("textbox", { name: "재추출 피드백", exact: true })
      .fill("원문에 있는 모집 직무가 누락됐습니다.");
    modalDecision = true;
    await dialog
      .getByRole("button", { name: "피드백 저장 및 재추출 요청", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".review-row")).toHaveCount(1);
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("RETRY_REQUESTED");
    await page
      .getByRole("button", { name: "검토 대기로 되돌리기", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "처리 상태", exact: true })
      .selectOption("OPEN");
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
