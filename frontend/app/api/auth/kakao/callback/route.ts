import { timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import {
  kakaoConfig,
  kakaoIdentity,
  KakaoServiceError,
} from "@/lib/server/kakao";
import { session } from "@/lib/server/store";
export const runtime = "nodejs";
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams,
    jar = await cookies();
  const saved = jar.get("career_kakao_state")?.value;
  jar.set("career_kakao_state", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth/kakao",
    maxAge: 0,
  });
  let config;
  try {
    config = kakaoConfig();
  } catch {}
  const base = config
    ? new URL(config.redirect).origin
    : new URL(request.url).origin;
  const fail = (error: string) =>
    Response.redirect(new URL(`/sign-in?error=${error}`, base), 303);
  const state = params.get("state");
  if (
    !saved ||
    !state ||
    !/^[a-f0-9]{64}$/.test(state) ||
    saved.length !== state.length ||
    !timingSafeEqual(Buffer.from(saved), Buffer.from(state))
  )
    return fail("kakao_state");
  if (params.has("error")) return fail("kakao_cancelled");
  const code = params.get("code");
  if (!code || code.length > 2000) return fail("kakao_failed");
  try {
    const id = await kakaoIdentity(code);
    await session(id);
    return Response.redirect(new URL("/analysis", base), 303);
  } catch (error) {
    if (error instanceof KakaoServiceError) {
      console.error("Kakao login failed", {
        stage: error.stage,
        status: error.status,
        providerCode: error.providerCode,
        transportCode: error.transportCode,
      });
      return fail(
        error.stage === "profile"
          ? "kakao_profile"
          : ["KOE010", "KOE101", "KOE114", "KOE127"].includes(
                error.providerCode || "",
              )
            ? "kakao_config"
            : "kakao_token",
      );
    }
    console.error("Kakao local account processing failed", {
      name: error instanceof Error ? error.name : "UnknownError",
    });
    return fail(
      error instanceof Error && error.message === "ACCOUNT_LINK_REQUIRED"
        ? "kakao_existing"
        : error instanceof Error && error.message === "EMAIL_CONSENT_REQUIRED"
          ? "kakao_email"
          : "kakao_failed",
    );
  }
}
