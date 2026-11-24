import { test, expect } from "@playwright/test";

test("demo login opens a workspace with sources and skills already filled", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "데모 계정으로 로그인" }).click();
  await expect(page).toHaveURL(/\/analysis$/);
  await expect(page.locator(".header-user")).toHaveText("김커리어님");
  await expect(page.getByLabel("공개 GitHub 저장소 URL")).toBeEnabled();
  const current = await (await page.request.get("/api/career")).json();
  expect(current.workspace.runs.length).toBeGreaterThanOrEqual(2);
  expect(current.workspace.documents.length).toBeGreaterThan(0);
  await expect(page.locator(".skill-row, .personal-radar-card")).toHaveCount(0);
  await page.goto("/my-data");
  await expect(page).toHaveURL(/\/analysis$/);
  expect((await page.request.get("/documents/demo-doc-resume")).ok()).toBe(
    true,
  );
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(
    page.getByRole("link", { name: "로그인", exact: true }),
  ).toBeVisible();
});

test("demo login rejects a wrong password", async ({ request, baseURL }) => {
  const r = await request.post("/api/account", {
    headers: { Origin: baseURL! },
    data: {
      action: "login",
      email: "demo@career.dev",
      password: "wrong-password-1",
    },
  });
  expect(r.ok()).toBe(false);
});
