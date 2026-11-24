import "server-only";
import { randomBytes, randomUUID } from "node:crypto";
import { accountByEmail, oauthAccount, createOAuthAccount } from "./accounts";
import { passwordHash } from "./store";
export function naverConfig() {
  const clientId = process.env.NAVER_CLIENT_ID,
    secret = process.env.NAVER_CLIENT_SECRET,
    redirect = process.env.NAVER_REDIRECT_URI;
  if (!clientId || !secret || !redirect) return null;
  const url = new URL(redirect);
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/api/auth/naver/callback" ||
    !(
      url.protocol === "https:" ||
      (url.protocol === "http:" &&
        ["localhost", "127.0.0.1"].includes(url.hostname))
    )
  )
    throw new Error("Invalid Naver redirect");
  return { clientId, secret, redirect };
}
async function naverRequest(url: string, init: RequestInit) {
  const response = await fetch(url, {
    ...init,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error("NAVER_PROVIDER_ERROR");
  return response.json();
}
export async function naverIdentity(code: string, state: string) {
  const config = naverConfig();
  if (!config) throw new Error("NAVER_NOT_CONFIGURED");
  const token = await naverRequest("https://nid.naver.com/oauth2.0/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      client_secret: config.secret,
      code,
      state,
      redirect_uri: config.redirect,
    }),
  });
  if (typeof token.access_token !== "string" || !token.access_token)
    throw new Error("NAVER_PROVIDER_ERROR");
  const profile = await naverRequest("https://openapi.naver.com/v1/nid/me", {
    headers: { Authorization: "Bearer " + token.access_token },
  });
  const identity = profile.response;
  if (
    profile.resultcode !== "00" ||
    typeof identity?.id !== "string" ||
    !identity.id.length ||
    identity.id.length > 128 ||
    /\s/.test(identity.id)
  )
    throw new Error("NAVER_PROVIDER_ERROR");
  const existing = await oauthAccount("naver", identity.id);
  if (existing) return existing;
  if (typeof identity.email !== "string")
    throw new Error("EMAIL_CONSENT_REQUIRED");
  const email = identity.email.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 200)
    throw new Error("EMAIL_CONSENT_REQUIRED");
  // A matching email alone is never sufficient to link a password/admin/Kakao account.
  if (await accountByEmail(email)) throw new Error("ACCOUNT_LINK_REQUIRED");
  return createOAuthAccount(
    {
      id: randomUUID(),
      email,
      name:
        String(identity.name || identity.nickname || "네이버 사용자")
          .trim()
          .slice(0, 60) || "네이버 사용자",
      password: passwordHash(randomBytes(32).toString("hex")),
    },
    identity.id,
    "naver",
  );
}
