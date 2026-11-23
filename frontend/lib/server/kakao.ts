import "server-only";
import { randomBytes, randomUUID } from "node:crypto";
import { passwordHash } from "./store";
import { accountByEmail, kakaoAccount, createKakaoAccount } from "./accounts";

export class KakaoServiceError extends Error {
  constructor(
    public readonly stage: "token" | "profile",
    public readonly status: number,
    public readonly providerCode: string | null,
    public readonly transportCode: string | null = null,
  ) {
    super(`Kakao ${stage} request failed`);
  }
}

async function kakaoRequest(
  url: string,
  init: RequestInit,
  stage: "token" | "profile",
) {
  try {
    return await fetch(url, init);
  } catch (error) {
    const cause = error instanceof Error ? error.cause : null;
    const code =
      cause && typeof cause === "object" && "code" in cause ? cause.code : null;
    throw new KakaoServiceError(
      stage,
      0,
      null,
      typeof code === "string" && /^[A-Z_]{1,40}$/.test(code)
        ? code
        : "NETWORK_ERROR",
    );
  }
}

async function serviceError(response: Response, stage: "token" | "profile") {
  const payload = await response.json().catch(() => null);
  // Kakao error descriptions can include app keys. Retain only the error code.
  const code = payload?.error_code;
  return new KakaoServiceError(
    stage,
    response.status,
    typeof code === "string" && /^KOE\d{3}$/.test(code) ? code : null,
  );
}

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
  const response = await kakaoRequest(
    "https://kauth.kakao.com/oauth/token",
    {
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
    },
    "token",
  );
  if (!response.ok) throw await serviceError(response, "token");
  const token = await response.json();
  if (typeof token.access_token !== "string") throw new Error("Missing token");
  const profile = await kakaoRequest(
    "https://kapi.kakao.com/v2/user/me",
    {
      headers: { Authorization: `Bearer ${token.access_token}` },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    },
    "profile",
  );
  if (!profile.ok) throw await serviceError(profile, "profile");
  const data = await profile.json();
  if (!Number.isSafeInteger(data.id) || data.id <= 0)
    throw new Error("Invalid identity");
  const subject = String(data.id),
    account = data.kakao_account || {};
  const existing = await kakaoAccount(subject);
  if (existing) return existing.id;
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
  if (await accountByEmail(email)) throw new Error("ACCOUNT_LINK_REQUIRED");
  const id = randomUUID(),
    name = String(account.profile?.nickname || "사용자").slice(0, 60);
  return (
    await createKakaoAccount(
      {
        id,
        email,
        name,
        password: passwordHash(randomBytes(32).toString("hex")),
      },
      subject,
    )
  ).id;
}
