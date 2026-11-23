import "server-only";
import { randomBytes, randomUUID } from "node:crypto";
import { db, passwordHash } from "./store";

export function kakaoConfig() {
  const clientId = process.env.KAKAO_REST_API_KEY,
    secret = process.env.KAKAO_CLIENT_SECRET,
    redirect = process.env.KAKAO_REDIRECT_URI;
  if (!clientId || !secret || !redirect) return null;
  const url = new URL(redirect);
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.pathname !== "/api/auth/kakao/callback" ||
    (url.protocol === "http:" &&
      !["localhost", "127.0.0.1"].includes(url.hostname))
  )
    throw new Error("Invalid Kakao redirect");
  return { clientId, secret, redirect };
}
export async function kakaoIdentity(code: string) {
  const config = kakaoConfig();
  if (!config) throw new Error("Not configured");
  const response = await fetch("https://kauth.kakao.com/oauth/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      client_secret: config.secret,
      redirect_uri: config.redirect,
      code,
    }),
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error("Token exchange failed");
  const token = await response.json();
  if (typeof token.access_token !== "string") throw new Error("Missing token");
  const profile = await fetch("https://kapi.kakao.com/v2/user/me", {
    headers: { Authorization: `Bearer ${token.access_token}` },
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10000),
  });
  if (!profile.ok) throw new Error("Profile request failed");
  const data = await profile.json();
  if (!Number.isSafeInteger(data.id) || data.id <= 0)
    throw new Error("Invalid identity");
  const subject = String(data.id),
    account = data.kakao_account || {};
  const d = db(),
    existing = d
      .prepare(
        "SELECT user_id FROM oauth_accounts WHERE provider='kakao' AND subject=?",
      )
      .get(subject) as { user_id: string } | undefined;
  if (existing) return existing.user_id;
  // Never attach a provider to an existing password/admin account based on email alone.
  if (
    !account.is_email_valid ||
    !account.is_email_verified ||
    typeof account.email !== "string"
  )
    throw new Error("EMAIL_CONSENT_REQUIRED");
  const email = account.email.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 200)
    throw new Error("Invalid email");
  if (d.prepare("SELECT id FROM users WHERE email=?").get(email))
    throw new Error("ACCOUNT_LINK_REQUIRED");
  const id = randomUUID(),
    name = String(account.profile?.nickname || "사용자").slice(0, 60);
  d.exec("BEGIN IMMEDIATE");
  try {
    d.prepare("INSERT INTO users VALUES(?,?,?,?)").run(
      id,
      email,
      name,
      passwordHash(randomBytes(32).toString("hex")),
    );
    d.prepare("INSERT INTO oauth_accounts VALUES('kakao',?,?)").run(
      subject,
      id,
    );
    d.exec("COMMIT");
  } catch (error) {
    d.exec("ROLLBACK");
    throw error;
  }
  return id;
}
