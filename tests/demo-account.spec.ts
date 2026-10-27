import { test, expect } from "@playwright/test";

test("demo login opens a workspace with sources and skills already filled", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "데모 계정으로 로그인" }).click();
  await expect(page).toHaveURL(/\/my-skills$/);
  await expect(page.locator(".header-user")).toHaveText("김커리어님");
  const sql = page
    .locator(".skill-card")
    .filter({ hasText: /^.*SQL.*$/ })
    .filter({ has: page.locator(".skill-card-name", { hasText: /^SQL$/ }) });
  await expect(sql).toContainText("심화 개선");
  await expect(sql.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    /^(8\d|9\d|100)$/,
  );
  await expect(page.locator(".skill-group h3").first()).toContainText(
    "Backend",
  );
  await page.goto("/my-skills?tab=tasks");
  await expect(page.locator(".growth-task")).toHaveCount(2);
  await page.goto("/my-data");
  await expect(page.getByText("발견한 근거 9개")).toBeVisible();
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
