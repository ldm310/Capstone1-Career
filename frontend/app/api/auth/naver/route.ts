import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { naverConfig } from "@/lib/server/naver";
import { loginDestination } from "@/lib/login-destination";
export const runtime = "nodejs";
export async function GET(request: Request) {
  let config;
  try {
    config = naverConfig();
  } catch {}
  if (!config)
    return Response.json(
      { error: "네이버 로그인 연결을 준비하고 있습니다." },
      { status: 503 },
    );
  const state = randomBytes(32).toString("hex"),
    jar = await cookies();
  const options = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    maxAge: 600,
  };
  jar.set("career_naver_state", state, { ...options, path: "/api/auth/naver" });
  jar.set(
    "career_naver_next",
    loginDestination(new URL(request.url).searchParams.get("next")),
    { ...options, path: "/" },
  );
  const url = new URL("https://nid.naver.com/oauth2.0/authorize");
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: config.clientId,
    redirect_uri: config.redirect,
    state,
  }).toString();
  return new Response(null, {
    status: 302,
    headers: { Location: url.href, "Cache-Control": "no-store" },
  });
}
