import { test, expect } from "@playwright/test";
import { loadEnvConfig } from "@next/env";
import { Client } from "pg";
import { DatabaseSync } from "node:sqlite";
import { randomBytes, randomUUID, createHash } from "node:crypto";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import path from "node:path";

test("RDS Kakao registration, password changes and email recovery preserve ownership and revoke sessions", async ({
  page,
  playwright,
}) => {
  test.skip(
    process.env.RUN_RDS_ACCOUNT_TESTS !== "1",
    "Explicit RDS account integration opt-in",
  );
  test.setTimeout(90000);
  loadEnvConfig(process.cwd(), true, { info() {}, error() {} });
  test.skip(
    process.env.CAREER_MAIL_TRANSPORT !== "file",
    "Recovery integration requires a file mailbox; this test must never send real email",
  );
  const base = "http://127.0.0.1:3000",
    headers = { origin: base };
  const namespace = process.env.CAREER_PROFILE_NAMESPACE || "local-review";
  const email = `security-${randomUUID()}@example.test`;
  const subject = "TEST-" + randomUUID();
  const token = randomBytes(32).toString("hex");
  const digest = createHash("sha256").update(token).digest("hex");
  const file = path.join(
    process.env.CAREER_DATA_DIR || ".career-data",
    "career.sqlite",
  );
  const connection = new Client({
    connectionString: process.env.CAREER_PROFILE_DATABASE_URL,
    ssl: {
      ca: readFileSync(process.env.CAREER_PROFILE_CA_FILE!, "utf8"),
      rejectUnauthorized: true,
    },
  });
  const other = await playwright.request.newContext({ baseURL: base });
  let id: string | undefined;
  await connection.connect();
  try {
    await page.context().addCookies([
      {
        name: "career_kakao_registration",
        value: token,
        url: base,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    await page.goto("/sign-in?provider=kakao"); // Creates the empty server-side handoff store.
    const local = new DatabaseSync(file);
    local
      .prepare("INSERT INTO kakao_registration VALUES(?,?,?,?,?,?,?,NULL)")
      .run(
        digest,
        subject,
        email,
        "RDS 카카오 검증",
        null,
        null,
        Date.now() + 600000,
      );
    local.close();
    await page.reload();
    await expect(page.getByLabel("이메일", { exact: true })).toHaveValue(email);
    await expect(page.getByLabel("이메일", { exact: true })).toHaveAttribute(
      "readonly",
      "",
    );
    const password = "rds-kakao-password-1";
    const registered = await page.request.post("/api/account", {
      headers,
      data: {
        action: "register",
        kakao: true,
        name: "RDS 카카오 검증",
        email,
        password,
        confirmation: password,
        age: 25,
        school: "검증대",
        major: "컴퓨터",
      },
    });
    expect(registered.status()).toBe(200);
    id = (await registered.json()).user.id;
    const stored = await connection.query(
      "SELECT a.subject_id,o.password_set_at,a.school FROM public.career_account a JOIN public.career_account_oauth o USING(namespace,subject_id) WHERE a.namespace=$1 AND a.subject_id=$2",
      [namespace, id],
    );
    expect(stored.rows[0].password_set_at).toBeTruthy();
    expect(stored.rows[0].school).toBe("검증대");
    expect(
      (
        await other.post("/api/account", {
          headers,
          data: { action: "login", email, password },
        })
      ).status(),
    ).toBe(200);
    const next = "rds-kakao-password-2";
    expect(
      (
        await page.request.post("/api/account", {
          headers,
          data: { action: "password", current: password, next },
        })
      ).status(),
    ).toBe(200);
    expect(
      (await (await page.request.get("/api/account")).json()).user.id,
    ).toBe(id);
    expect((await (await other.get("/api/account")).json()).user).toBeNull();
    expect(
      (
        await other.post("/api/account", {
          headers,
          data: { action: "login", email, password },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await page.request.post("/api/account/recovery", {
          headers,
          data: { email },
        })
      ).status(),
    ).toBe(200);
    let resetToken = "";
    await expect
      .poll(() => {
        const folder = path.join(
          process.env.CAREER_DATA_DIR || ".career-data",
          "mailbox",
        );
        if (!existsSync(folder)) return false;
        for (const name of readdirSync(folder).filter((name) =>
          name.endsWith(".json"),
        )) {
          const mail = JSON.parse(
            readFileSync(path.join(folder, name), "utf8"),
          );
          if (mail.to === email)
            resetToken = mail.text.match(/#token=([a-f0-9]{64})/)[1];
        }
        return !!resetToken;
      })
      .toBe(true);
    const recovered = "rds-kakao-password-3";
    expect(
      (
        await other.post("/api/account/password-reset", {
          headers,
          data: {
            token: resetToken,
            password: recovered,
            confirmation: recovered,
          },
        })
      ).status(),
    ).toBe(200);
    expect(
      (await (await page.request.get("/api/account")).json()).user,
    ).toBeNull();
    expect(
      (
        await other.post("/api/account", {
          headers,
          data: { action: "login", email, password: recovered },
        })
      ).status(),
    ).toBe(200);
    expect(
      (
        await other.post("/api/account/password-reset", {
          headers,
          data: { token: resetToken, password: next, confirmation: next },
        })
      ).status(),
    ).toBe(400);
  } finally {
    const owned = await connection.query(
      "SELECT subject_id FROM public.career_account WHERE namespace=$1 AND email=$2",
      [namespace, email],
    );
    await connection.query(
      "DELETE FROM public.career_account WHERE namespace=$1 AND email=$2",
      [namespace, email],
    );
    const local = new DatabaseSync(file);
    local
      .prepare("DELETE FROM kakao_registration WHERE token_hash=?")
      .run(digest);
    for (const account of owned.rows) {
      for (const table of [
        "sessions",
        "profiles",
        "workspaces",
        "password_reset_tokens",
      ]) {
        if (
          local
            .prepare(
              "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            )
            .get(table)
        )
          local
            .prepare(`DELETE FROM ${table} WHERE user_id=?`)
            .run(account.subject_id);
      }
      local.prepare("DELETE FROM users WHERE id=?").run(account.subject_id);
    }
    local.close();
    await other.dispose();
    await connection.end();
  }
});
