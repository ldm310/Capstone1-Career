import { test, expect } from "@playwright/test";

test("demo login opens a workspace with sources and skills already filled", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "데모 계정으로 로그인" }).click();
  await expect(page).toHaveURL(/\/my-skills$/);
  await expect(page.locator(".header-user")).toHaveText("김커리어님");
  const sql = page.getByRole("button", { name: /^SQL LV \d+ / });
  await expect(sql).toHaveAccessibleName(/심화 개선 자세히$/);
  await expect(sql.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    /^(8\d|9\d|100)$/,
  );
  // 분야별 묶음 없이 한 목록에 점수가 높은 순서로 보여준다.
  await expect(page.locator(".skill-group")).toHaveCount(0);
  const levels = await page
    .locator(".skill-row [role=progressbar]")
    .evaluateAll((bars) =>
      bars.map((b) => Number(b.getAttribute("aria-valuenow"))),
    );
  expect(levels.length).toBeGreaterThan(5);
  expect(levels).toEqual([...levels].sort((a, b) => b - a));
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
