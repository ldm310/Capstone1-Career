import { test, expect } from "@playwright/test";
import { mockPublicJobs } from "./public-jobs-fixture";

test("no signup: sources, saved results and every workspace menu are accessible", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/career?tab=sources");
  await expect(
    page.getByText(/로그인 없이 이용 중 · 게스트 공간/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "지금까지 해온 것을 알려주세요" }),
  ).toBeVisible();
  await page.getByLabel("파일 선택").setInputFiles({
    name: "guest-project.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# 프로젝트\nPython으로 API를 개발했습니다. Docker 컨테이너로 배포하고 SQL을 사용했습니다.",
    ),
  });
  await page.getByRole("button", { name: "파일 저장하고 분석하기" }).click();
  await expect(page.getByText("게스트 공간에 저장했어요.")).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("guest-project.md", { exact: true }).first(),
  ).toBeVisible();
  const before = (await (await page.request.get("/api/career")).json()).user.id;
  for (const tab of [
    "overview",
    "skills",
    "tasks",
    "ranking",
    "jobs",
    "plan",
    "schedule",
    "applications",
    "interview",
    "share",
  ]) {
    await page.goto(`/career?tab=${tab}`);
    await expect(
      page.getByText(/로그인 없이 이용 중 · 게스트 공간/),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "계정 만들기", exact: true }),
    ).toHaveCount(0);
    await expect(page.locator(".career-workspace [role=alert]")).toHaveCount(0);
  }
  await page.goto("/sign-in");
  await expect(page).toHaveURL(/\/growth$/);
  expect((await (await page.request.get("/api/career")).json()).user.id).toBe(
    before,
  );
});

test("guest sessions isolate documents and cannot enter real rankings", async ({
  browser,
  baseURL,
}) => {
  const first = await browser.newContext(),
    second = await browser.newContext();
  const headers = { Origin: baseURL! };
  const a = await first.request.post(`${baseURL}/api/guest`, { headers });
  const b = await second.request.post(`${baseURL}/api/guest`, { headers });
  expect(a.ok()).toBeTruthy();
  expect(b.ok()).toBeTruthy();
  const userA = (await a.json()).user.id;
  expect((await b.json()).user.id).not.toBe(userA);
  const upload = await first.request.post(`${baseURL}/api/documents`, {
    headers,
    multipart: {
      file: {
        name: "private.md",
        mimeType: "text/plain",
        buffer: Buffer.from("Python 프로젝트와 Docker 배포를 개발했습니다."),
      },
      source: "cv",
    },
  });
  const doc = (await upload.json()).workspace.documents[0].id;
  expect(
    (await second.request.get(`${baseURL}/api/documents/${doc}`)).status(),
  ).toBe(404);
  const settings = await first.request.post(`${baseURL}/api/growth`, {
    headers,
    data: { action: "settings", nickname: "게스트 검증", publicRanking: true },
  });
  expect(settings.ok()).toBeTruthy();
  const growth = await (
    await first.request.get(`${baseURL}/api/growth`)
  ).json();
  expect(growth.ranking.some((row: { id: string }) => row.id === userA)).toBe(
    false,
  );
  expect(growth.growth.rewards).toHaveLength(0);
  expect(
    (
      await first.request.post(`${baseURL}/api/guest`, {
        headers: { Origin: "https://other.example" },
      })
    ).ok(),
  ).toBe(false);
  await first.close();
  await second.close();
});
