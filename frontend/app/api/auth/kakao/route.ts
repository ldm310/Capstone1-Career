import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { kakaoConfig } from "@/lib/server/kakao";
export const runtime = "nodejs";
export async function GET() {
  let config;
  try {
    config = kakaoConfig();
  } catch {}
  if (!config)
    return Response.json(
      { error: "카카오 로그인 연결을 준비하고 있습니다." },
      { status: 503 },
    );
  const state = randomBytes(32).toString("hex"),
    jar = await cookies();
  jar.set("career_kakao_state", state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth/kakao",
    maxAge: 600,
  });
  const url = new URL("https://kauth.kakao.com/oauth/authorize");
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: config.clientId,
    redirect_uri: config.redirect,
    state,
  }).toString();
  return Response.redirect(url, 302);
}
