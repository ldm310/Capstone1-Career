import { test, expect } from "@playwright/test";

test("login accepts email only and shows readable validation errors", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await expect(page.getByLabel("이메일", { exact: true })).toHaveAttribute(
    "type",
    "email",
  );
  await expect(
    page.getByText("이메일 또는 아이디", { exact: true }),
  ).toHaveCount(0);
  const invalid = await page.request.post("/api/account", {
    headers: { origin: "http://127.0.0.1:3000" },
    data: { action: "login", email: "admin", password: "test-password" },
  });
  expect(invalid.status()).toBe(400);
  expect(await invalid.json()).toEqual({
    error: "이메일 형식을 확인해 주세요.",
  });
  const register = await page.request.post("/api/account", {
    headers: { origin: "http://127.0.0.1:3000" },
    data: {
      action: "register",
      email: "validation-only@example.test",
      name: "검증",
      password: "short",
    },
  });
  expect(register.status()).toBe(400);
  expect(await register.json()).toEqual({
    error: "비밀번호는 10자 이상 입력해 주세요.",
  });
});
