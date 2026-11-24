import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { loadEnvConfig } from "@next/env";
import { Client } from "pg";

test("registration persists optional fields and credentials in RDS", async ({
  page,
  playwright,
}) => {
  test.skip(
    process.env.RUN_RDS_ACCOUNT_TESTS !== "1",
    "Explicit RDS integration opt-in",
  );
  loadEnvConfig(process.cwd(), false, { info() {}, error() {} });
  const connection = new Client({
    connectionString: process.env.CAREER_PROFILE_DATABASE_URL,
    ssl: {
      ca: readFileSync(process.env.CAREER_PROFILE_CA_FILE!, "utf8"),
      rejectUnauthorized: true,
    },
    connectionTimeoutMillis: 5000,
  });
  const namespace = process.env.CAREER_PROFILE_NAMESPACE || "local-review";
  const email = `registration-${randomUUID()}@example.test`;
  const minimalEmail = `minimal-${randomUUID()}@example.test`;
  const password = randomUUID();
  const nextPassword = randomUUID();
  const ids: string[] = [];
  const base = "http://127.0.0.1:3000";
  const client = await playwright.request.newContext({
    baseURL: base,
    extraHTTPHeaders: { origin: base },
  });
  await connection.connect();
  try {
    await page.goto("/sign-in");
    await expect(
      page.getByText("처음 이용하면 카카오 계정으로 가입됩니다."),
    ).toHaveCount(0);
    await expect(
      page.getByText("이메일 또는 카카오 계정으로 가입할 수 있습니다."),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "회원가입", exact: true }).click();
    await expect(
      page.getByText("이메일 또는 카카오 계정으로 가입할 수 있습니다."),
    ).toBeVisible();
    await page.getByLabel("이름", { exact: true }).fill("가입 검증");
    await page.getByLabel("이메일", { exact: true }).fill(email);
    await page.getByLabel("비밀번호", { exact: true }).fill(password);
    await page.getByLabel("비밀번호 확인", { exact: true }).fill(password);
    await page.getByLabel("나이 (선택)", { exact: true }).fill("24");
    await page.getByLabel("학교 (선택)", { exact: true }).fill("검증대학교");
    await page.getByLabel("학과 (선택)", { exact: true }).fill("컴퓨터공학과");
    await page
      .getByRole("button", { name: "가입하고 분석 시작하기", exact: true })
      .click();
    await expect(page).toHaveURL(/\/analysis$/);
    const account = await (await page.request.get("/api/account")).json();
    ids.push(account.user.id);
    expect(account.user).not.toHaveProperty("password");
    expect(account.profile).toMatchObject({
      age: 24,
      school: "검증대학교",
      major: "컴퓨터공학과",
    });
    const stored = await connection.query(
      `SELECT age,school,major,(password_hash <> $3 AND position(':' in password_hash)>0) AS hashed FROM public.career_account WHERE namespace=$1 AND email=$2`,
      [namespace, email, password],
    );
    expect(stored.rows).toEqual([
      { age: 24, school: "검증대학교", major: "컴퓨터공학과", hashed: true },
    ]);
    const loggedIn = await client.post("/api/account", {
      data: { action: "login", email, password },
    });
    expect(loggedIn.status()).toBe(200);
    const changed = await client.post("/api/account", {
      data: { action: "password", current: password, next: nextPassword },
    });
    expect(changed.status()).toBe(200);
    await client.post("/api/account", { data: { action: "logout" } });
    expect(
      (
        await client.post("/api/account", {
          data: { action: "login", email, password },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await client.post("/api/account", {
          data: { action: "login", email, password: nextPassword },
        })
      ).status(),
    ).toBe(200);
    const cleared = await client.post("/api/account", {
      data: {
        action: "update",
        name: account.user.name,
        email,
        profile: { ...account.profile, age: null, school: "", major: "" },
      },
    });
    expect(cleared.status()).toBe(200);
    expect(
      (await (await client.get("/api/account")).json()).profile,
    ).toMatchObject({ age: null, school: "", major: "" });
    expect(
      (
        await client.post("/api/account", {
          data: { action: "register", email, password, name: "중복" },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await client.post("/api/account", {
          data: {
            action: "register",
            email: minimalEmail,
            password,
            name: "최소",
            age: 24.5,
          },
        })
      ).status(),
    ).toBe(400);
    const minimal = await client.post("/api/account", {
      data: { action: "register", email: minimalEmail, password, name: "최소" },
    });
    expect(minimal.status()).toBe(200);
    ids.push((await minimal.json()).user.id);
    const optional = await connection.query(
      "SELECT age,school,major FROM public.career_account WHERE namespace=$1 AND email=$2",
      [namespace, minimalEmail],
    );
    expect(optional.rows).toEqual([{ age: null, school: "", major: "" }]);
  } finally {
    // Remove only the two accounts created by this test, even after an assertion fails.
    const created = await connection.query(
      "SELECT subject_id FROM public.career_account WHERE namespace=$1 AND email=ANY($2::text[])",
      [namespace, [email, minimalEmail]],
    );
    ids.push(...created.rows.map((row) => row.subject_id));
    await connection.query(
      "DELETE FROM public.career_account WHERE namespace=$1 AND email=ANY($2::text[])",
      [namespace, [email, minimalEmail]],
    );
    const local = new DatabaseSync(
      path.join(process.env.CAREER_DATA_DIR || ".career-data", "career.sqlite"),
    );
    for (const id of new Set(ids)) {
      for (const table of ["sessions", "profiles", "workspaces"])
        local.prepare(`DELETE FROM ${table} WHERE user_id=?`).run(id);
      local.prepare("DELETE FROM users WHERE id=?").run(id);
    }
    local.close();
    await client.dispose();
    await connection.end();
  }
});
