import { test, expect } from "@playwright/test";
import { mockPublicJobs } from "./public-jobs-fixture";

test("no signup: sources, saved results and every section tab are accessible", async ({
  page,
}) => {
  await mockPublicJobs(page);
  await page.goto("/my-data");
  await expect(page.getByText("게스트 공간, 7일 보관")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "자료 추가", exact: true }),
  ).toBeVisible();
  await page.getByLabel("파일 선택").setInputFiles({
    name: "guest-project.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# 프로젝트\nPython으로 API를 개발했습니다. Docker 컨테이너로 배포하고 SQL을 사용했습니다.",
    ),
  });
  await page.getByRole("button", { name: "저장하고 분석하기" }).click();
  await expect(page.getByText("저장했어요.")).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("guest-project.md", { exact: true }).first(),
  ).toBeVisible();
  const before = (await (await page.request.get("/api/career")).json()).user.id;
  for (const url of [
    "/my-skills",
    "/my-skills?tab=next",
    "/my-data?tab=share",
  ]) {
    await page.goto(url);
    await expect(page.getByText("게스트 공간, 7일 보관")).toBeVisible();
    await expect(page.locator(".career-workspace [role=alert]")).toHaveCount(0);
  }
  await page.goto("/sign-in");
  await expect(
    page.getByRole("heading", { name: "로그인", exact: true }),
  ).toBeVisible();
  expect((await (await page.request.get("/api/career")).json()).user.id).toBe(
    before,
  );
});

test("guest sessions isolate documents", async ({ browser, baseURL }) => {
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
