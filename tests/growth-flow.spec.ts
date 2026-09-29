import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { randomUUID } from "node:crypto";
test("sample: criteria, fixed reward, submission, history, private ranking and responsive layout", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", {
      name: "해온 것을 확인하고, 다음 단계를 준비해요.",
    }),
  ).toBeVisible();
  const card = page
    .locator(".growth-skill")
    .filter({
      has: page.getByRole("heading", { name: "Docker", exact: true }),
    });
  await card.getByRole("button", { name: "근거·과제 확인하기" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", { name: "LV2 과제 시작 · 완료 확인 후 20점" })
    .click();
  await page.getByRole("button", { name: "상세 닫기" }).click();
  const task = page.locator(".growth-task").first();
  await task
    .getByLabel("새 작업의 근거")
    .fill("https://github.com/example/project/commit/demo");
  await task
    .getByLabel("무엇을 새로 구현했나요?")
    .fill("앱과 DB 연결, 설정 분리, 데이터 유지 및 실행 결과를 정리했습니다.");
  await task.getByRole("button", { name: "샘플 완료 결과 보기" }).click();
  await expect(page.getByText("+20점", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("+20점", { exact: true })).toBeVisible();
  await expect(page.getByText("랭킹 미참여 · 내 포인트 20점")).toBeVisible();
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "work/growth-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.screenshot({ path: "work/growth-dashboard.png", fullPage: true });
});
test("account: old evidence gets no rewards, mutations cannot award points, new inputs and ranking privacy", async ({
  request,
  baseURL,
}) => {
  const headers = { Origin: baseURL! };
  const signup = await request.post("/api/account", {
    headers,
    data: {
      action: "register",
      name: "성장 검증",
      email: `growth-test-${randomUUID()}@example.com`,
      password: "Growth-test-2026!",
    },
  });
  expect(signup.ok()).toBeTruthy();
  const upload = await request.post("/api/documents", {
    headers,
    multipart: {
      file: {
        name: "notes.md",
        mimeType: "text/markdown",
        buffer: Buffer.from(
          "# Notes\nDocker 프로젝트와 postgres 데이터베이스 구현 기록입니다.",
        ),
      },
      source: "notion",
    },
  });
  expect(upload.ok()).toBeTruthy();
  const denied = await request.post("/api/documents", {
    headers,
    multipart: {
      file: {
        name: "notes.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Docker project implementation notes"),
      },
    },
  });
  expect(denied.ok()).toBeFalsy();
  let data = await (await request.get("/api/growth")).json();
  expect(data.growth.rewards).toHaveLength(0);
  expect(
    data.growth.reviews.some(
      (r: { skill: string }) => r.skill === "PostgreSQL",
    ),
  ).toBeTruthy();
  for (let i = 0; i < 2; i++) {
    expect(
      (
        await request.post("/api/growth", {
          headers,
          data: { action: "start", skill: "Docker", level: 1 },
        })
      ).ok(),
    ).toBeTruthy();
  }
  data = await (await request.get("/api/growth")).json();
  expect(data.growth.tasks).toHaveLength(1);
  await request.post("/api/growth", {
    headers,
    data: {
      action: "submit",
      id: data.growth.tasks[0].id,
      evidence: "old project",
      explanation: "기존 프로젝트의 자료를 추가로 제출합니다.",
    },
  });
  data = await (await request.get("/api/growth")).json();
  expect(data.growth.rewards).toHaveLength(0);
  expect(data.growth.tasks[0].status).toBe("needs_evidence");
  expect(
    (
      await request.post("/api/growth", {
        headers,
        data: { action: "award", points: 999 },
      })
    ).ok(),
  ).toBeFalsy();
  expect(
    data.ranking.some((r: { id: string }) => r.id === data.userId),
  ).toBeFalsy();
  await request.post("/api/growth", {
    headers,
    data: { action: "settings", nickname: "테스트 공개", publicRanking: true },
  });
  data = await (await request.get("/api/growth")).json();
  expect(
    data.ranking.some((r: { id: string }) => r.id === data.userId),
  ).toBeTruthy();
  await request.post("/api/growth", {
    headers,
    data: { action: "settings", nickname: "테스트 공개", publicRanking: false },
  });
});
