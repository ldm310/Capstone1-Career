import { test, expect, type APIRequestContext } from "@playwright/test";
import { DatabaseSync } from "node:sqlite";
import { randomUUID, createHash, scryptSync, randomBytes } from "node:crypto";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import path from "node:path";

const base = "http://127.0.0.1:3108";
const headers = { origin: base };
const firstPassword = "first-password-2026";
function directory() {
  return JSON.parse(readFileSync("work/auth-test-current.json", "utf8"))
    .directory as string;
}
function local() {
  return new DatabaseSync(path.join(directory(), "career.sqlite"));
}
function hash(value: string) {
  return createHash("sha256").update(value).digest("hex");
}
async function register(client: APIRequestContext, email: string) {
  const r = await client.post("/api/account", {
    headers,
    data: {
      action: "register",
      email,
      name: "계정 검증",
      password: firstPassword,
    },
  });
  expect(r.status()).toBe(200);
  return (await r.json()).user;
}
async function kakao(
  client: APIRequestContext,
  email: string,
  subject: number,
  verified = true,
  destination?: string,
) {
  const start = await client.get(
    "/api/auth/kakao" +
      (destination ? "?" + new URLSearchParams({ next: destination }) : ""),
    { maxRedirects: 0 },
  );
  expect(start.status()).toBe(302);
  const state = new URL(start.headers().location).searchParams.get("state")!;
  const code = Buffer.from(
    JSON.stringify({ email, subject, verified }),
  ).toString("base64url");
  return client.get(
    "/api/auth/kakao/callback?" + new URLSearchParams({ state, code }),
    { maxRedirects: 0 },
  );
}
async function mail(email: string) {
  let found: { text: string } | undefined;
  await expect
    .poll(() => {
      const box = path.join(directory(), "mailbox");
      if (!existsSync(box)) return false;
      for (const file of readdirSync(box).filter((file) =>
        file.endsWith(".json"),
      )) {
        const item = JSON.parse(readFileSync(path.join(box, file), "utf8"));
        if (item.to === email) found = item;
      }
      return !!found;
    })
    .toBe(true);
  return found!.text.match(/http[^\s]+#token=([a-f0-9]{64})/)![0];
}
test.beforeEach(async ({ page }) => {
  expect((await page.request.post("/api/guest", { headers })).status()).toBe(
    200,
  );
});

test("optional email verification proves ownership once without changing login requirements", async ({
  page,
  playwright,
}) => {
  const email = `verification-${randomUUID()}@example.test`;
  await register(page.request, email);
  expect(
    (await (await page.request.get("/api/account/email-verification")).json())
      .verified,
  ).toBe(false);
  expect(
    (
      await page.request.post("/api/account/email-verification", {
        headers,
        data: { action: "request" },
      })
    ).status(),
  ).toBe(200);
  const link = await mail(email);
  const token = new URLSearchParams(new URL(link).hash.slice(1)).get("token")!;
  const database = local();
  expect(
    database.prepare("SELECT token_hash FROM email_verifications").get()
      ?.token_hash,
  ).toBe(hash(token));
  database.close();
  const anonymous = await playwright.request.newContext({ baseURL: base });
  try {
    expect(
      (
        await anonymous.post("/api/account/email-verification", {
          headers,
          data: { action: "request" },
        })
      ).status(),
    ).toBe(401);
    await page.goto(link);
    await page
      .getByRole("button", { name: "이메일 인증 완료", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText(
      "이메일 인증이 완료됐습니다.",
    );
    expect(
      (await (await page.request.get("/api/account/email-verification")).json())
        .verified,
    ).toBe(true);
    expect(
      (
        await anonymous.post("/api/account/email-verification", {
          headers,
          data: { action: "confirm", token },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await anonymous.post("/api/account", {
          headers,
          data: { action: "login", email, password: firstPassword },
        })
      ).status(),
    ).toBe(200);
  } finally {
    await anonymous.dispose();
  }
});

test("Kakao login and password-setup signup preserve a safe posting destination", async ({
  page,
}) => {
  const email = `return-kakao-${randomUUID()}@example.test`;
  const account = await register(page.request, email);
  let database = local();
  database
    .prepare(
      "INSERT INTO oauth_accounts(provider,subject,user_id,password_set_at) VALUES('kakao',?,?,?)",
    )
    .run("119001", account.id, Date.now());
  database.close();
  const target = "/jobs?q=Backend&limit=24&job=fixture-0&view=stats";
  const existing = await kakao(page.request, email, 119001, true, target);
  expect(existing.headers().location).toBe(base + target);
  const rejected = await kakao(
    page.request,
    email,
    119001,
    true,
    "https://evil.example",
  );
  expect(rejected.headers().location).toBe(base + "/analysis");
  const fresh = await kakao(
    page.request,
    `return-new-${randomUUID()}@example.test`,
    119002,
    true,
    target,
  );
  expect(new URL(fresh.headers().location).searchParams.get("next")).toBe(
    target,
  );
  await page.goto(fresh.headers().location);
  await page.getByLabel("비밀번호", { exact: true }).fill(firstPassword);
  await page.getByLabel("비밀번호 확인", { exact: true }).fill(firstPassword);
  await page
    .getByRole("button", { name: "가입하고 분석 시작하기", exact: true })
    .click();
  await expect(page).toHaveURL(base + target);
});

test("password change keeps the current browser and rejects other or restored old sessions", async ({
  page,
  playwright,
}) => {
  const email = `change-${randomUUID()}@example.test`;
  const account = await register(page.request, email);
  const other = await playwright.request.newContext({ baseURL: base });
  try {
    expect(
      (
        await other.post("/api/account", {
          headers,
          data: { action: "login", email, password: firstPassword },
        })
      ).status(),
    ).toBe(200);
    const before = local();
    const sessions = before
      .prepare("SELECT * FROM sessions WHERE user_id=?")
      .all(account.id);
    before.close();
    const next = "next-password-2026";
    expect(
      (
        await page.request.post("/api/account", {
          headers,
          data: { action: "password", current: firstPassword, next },
        })
      ).status(),
    ).toBe(200);
    expect(
      (await (await page.request.get("/api/account")).json()).user.id,
    ).toBe(account.id);
    expect((await (await other.get("/api/account")).json()).user).toBeNull();
    // Model an old persisted session on another node: the password stamp still rejects it.
    const restored = local();
    for (const session of sessions)
      restored
        .prepare(
          "INSERT OR IGNORE INTO sessions(token,user_id,expires,credential_stamp) VALUES(?,?,?,?)",
        )
        .run(
          session.token as string,
          session.user_id as string,
          session.expires as number,
          session.credential_stamp as string,
        );
    restored.close();
    expect((await (await other.get("/api/account")).json()).user).toBeNull();
    expect(
      (
        await other.post("/api/account", {
          headers,
          data: { action: "login", email, password: firstPassword },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await other.post("/api/account", {
          headers,
          data: { action: "login", email, password: next },
        })
      ).status(),
    ).toBe(200);
  } finally {
    await other.dispose();
  }
});

test("Kakao registration fixes the verified email and requires a selected password before account creation", async ({
  page,
  playwright,
}) => {
  const email = `kakao-${randomUUID()}@example.test`;
  const subject = 110001;
  const callback = await kakao(page.request, email, subject);
  expect(callback.status()).toBe(303);
  expect(callback.headers().location).toContain("/sign-in?provider=kakao");
  expect(
    (await (await page.request.get("/api/account")).json()).user,
  ).toBeNull();
  let database = local();
  expect(
    database.prepare("SELECT id FROM users WHERE email=?").get(email),
  ).toBeUndefined();
  database.close();
  const payload = {
    action: "register",
    kakao: true,
    name: "카카오 가입 검증",
    email,
    password: "chosen-password-2026",
    confirmation: "chosen-password-2026",
    age: 24,
    school: "검증대학교",
    major: "컴퓨터공학",
  };
  expect(
    (
      await page.request.post("/api/account", {
        headers,
        data: { ...payload, email: "tampered@example.test" },
      })
    ).status(),
  ).toBe(400);
  await page.goto("/sign-in?provider=kakao");
  await expect(page.getByLabel("이메일", { exact: true })).toHaveValue(email);
  await expect(page.getByLabel("이메일", { exact: true })).toHaveAttribute(
    "readonly",
    "",
  );
  await page.getByLabel("이름", { exact: true }).fill(payload.name);
  await page.getByLabel("비밀번호", { exact: true }).fill(payload.password);
  await page
    .getByLabel("비밀번호 확인", { exact: true })
    .fill(payload.password);
  await page.getByLabel("나이 (선택)", { exact: true }).fill("24");
  await page.getByLabel("학교 (선택)", { exact: true }).fill(payload.school);
  await page.getByLabel("학과 (선택)", { exact: true }).fill(payload.major);
  await page
    .getByRole("button", { name: "가입하고 분석 시작하기", exact: true })
    .click();
  await expect(page).toHaveURL(/\/analysis$/);
  const account = await (await page.request.get("/api/account")).json();
  expect(account.user.email).toBe(email);
  expect(account.user).not.toHaveProperty("password");
  expect(account.profile.school).toBe(payload.school);
  expect(
    (
      await page.request.post("/api/account", { headers, data: payload })
    ).status(),
  ).toBe(400);
  database = local();
  const saved = database
    .prepare("SELECT password FROM users WHERE email=?")
    .get(email) as { password: string };
  const [salt, digest] = saved.password.split(":");
  expect(scryptSync(payload.password, salt, 64).toString("hex")).toBe(digest);
  expect(
    database
      .prepare("SELECT password_set_at FROM oauth_accounts WHERE subject=?")
      .get(String(subject)),
  ).toMatchObject({ password_set_at: expect.any(Number) });
  database.close();
  const another = await playwright.request.newContext({ baseURL: base });
  try {
    expect(
      (
        await another.post("/api/account", {
          headers,
          data: { action: "login", email, password: payload.password },
        })
      ).status(),
    ).toBe(200);
    const again = await kakao(another, email, subject);
    expect(again.headers().location).toBe(base + "/analysis");
  } finally {
    await another.dispose();
  }
});

test("legacy Kakao users set a password on the same account; missing proof and consent are rejected", async ({
  page,
}) => {
  const email = `legacy-${randomUUID()}@example.test`;
  const id = randomUUID();
  const subject = 110002;
  const salt = randomBytes(16).toString("hex");
  const password =
    salt + ":" + scryptSync(randomUUID(), salt, 64).toString("hex");
  const database = local();
  database
    .prepare("INSERT INTO users(id,email,name,password) VALUES(?,?,?,?)")
    .run(id, email, "기존 카카오 회원", password);
  database
    .prepare(
      "INSERT INTO oauth_accounts(provider,subject,user_id,password_set_at) VALUES('kakao',?,?,NULL)",
    )
    .run(String(subject), id);
  database.close();
  const invalid = await kakao(
    page.request,
    "missing-consent@example.test",
    110003,
    false,
  );
  expect(invalid.headers().location).toContain("kakao_email");
  const result = await kakao(page.request, email, subject);
  expect(result.headers().location).toContain("provider=kakao");
  await page.goto("/sign-in?provider=kakao");
  await expect(
    page.getByRole("heading", { name: "비밀번호 설정", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("비밀번호", { exact: true })
    .fill("legacy-new-password-2026");
  await page
    .getByLabel("비밀번호 확인", { exact: true })
    .fill("legacy-new-password-2026");
  await page
    .getByRole("button", { name: "비밀번호 설정 완료", exact: true })
    .click();
  await expect(page).toHaveURL(/\/analysis$/);
  expect((await (await page.request.get("/api/account")).json()).user.id).toBe(
    id,
  );
  const replay = await page.request.post("/api/account", {
    headers,
    data: {
      action: "register",
      kakao: true,
      name: "다시",
      email,
      password: firstPassword,
      confirmation: firstPassword,
    },
  });
  expect(replay.status()).toBe(400);
});

test("email recovery hides account existence, resets once, and revokes every session", async ({
  page,
  playwright,
}) => {
  const email = `recover-${randomUUID()}@example.test`;
  const account = await register(page.request, email);
  const other = await playwright.request.newContext({ baseURL: base });
  try {
    await other.post("/api/account", {
      headers,
      data: { action: "login", email, password: firstPassword },
    });
    expect(
      (
        await page.request.post("/api/account/recovery", {
          headers: { origin: "https://invalid.example" },
          data: { email },
        })
      ).status(),
    ).toBe(403);
    const unknown = await page.request.post("/api/account/recovery", {
      headers,
      data: { email: `unknown-${randomUUID()}@example.test` },
    });
    const known = await page.request.post("/api/account/recovery", {
      headers,
      data: { email },
    });
    expect(known.status()).toBe(200);
    expect(await known.json()).toEqual(await unknown.json());
    expect(await known.json()).not.toHaveProperty("token");
    const link = await mail(email);
    const token = new URLSearchParams(new URL(link).hash.slice(1)).get(
      "token",
    )!;
    const database = local();
    expect(
      database
        .prepare("SELECT token_hash FROM password_reset_tokens WHERE user_id=?")
        .get(account.id),
    ).toMatchObject({ token_hash: hash(token) });
    database.close();
    const mismatch = await page.request.post("/api/account/password-reset", {
      headers,
      data: {
        token,
        password: "reset-password-2026",
        confirmation: "different-password",
      },
    });
    expect(mismatch.status()).toBe(400);
    await page.goto(link);
    await expect(page).not.toHaveURL(/#token=/);
    await page
      .getByLabel("새 비밀번호", { exact: true })
      .fill("reset-password-2026");
    await page
      .getByLabel("비밀번호 확인", { exact: true })
      .fill("reset-password-2026");
    await page
      .getByRole("button", { name: "비밀번호 변경", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "비밀번호 변경 완료", exact: true }),
    ).toBeVisible();
    expect(
      (await (await page.request.get("/api/account")).json()).user,
    ).toBeNull();
    expect((await (await other.get("/api/account")).json()).user).toBeNull();
    expect(
      (
        await other.post("/api/account/password-reset", {
          headers,
          data: { token, password: firstPassword, confirmation: firstPassword },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await other.post("/api/account", {
          headers,
          data: { action: "login", email, password: "reset-password-2026" },
        })
      ).status(),
    ).toBe(200);
  } finally {
    await other.dispose();
  }
});

test("expired recovery and Kakao registration tickets cannot change or create accounts", async ({
  page,
}) => {
  const email = `expired-${randomUUID()}@example.test`;
  await register(page.request, email);
  await page.request.post("/api/account/recovery", {
    headers,
    data: { email },
  });
  const link = await mail(email);
  const token = new URLSearchParams(new URL(link).hash.slice(1)).get("token")!;
  let database = local();
  database
    .prepare("UPDATE password_reset_tokens SET expires=? WHERE token_hash=?")
    .run(Date.now() - 1, hash(token));
  database.close();
  expect(
    (
      await page.request.post("/api/account/password-reset", {
        headers,
        data: { token, password: firstPassword, confirmation: firstPassword },
      })
    ).status(),
  ).toBe(400);
  const pendingEmail = `expired-kakao-${randomUUID()}@example.test`;
  await kakao(page.request, pendingEmail, 110004);
  database = local();
  database
    .prepare("UPDATE kakao_registration SET expires=? WHERE email=?")
    .run(Date.now() - 1, pendingEmail);
  database.close();
  expect(
    (
      await page.request.post("/api/account", {
        headers,
        data: {
          action: "register",
          kakao: true,
          name: "만료",
          email: pendingEmail,
          password: firstPassword,
          confirmation: firstPassword,
        },
      })
    ).status(),
  ).toBe(400);
  database = local();
  expect(
    database.prepare("SELECT id FROM users WHERE email=?").get(pendingEmail),
  ).toBeUndefined();
  database.close();
});
