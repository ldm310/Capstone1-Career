import { timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { naverConfig, naverIdentity } from "@/lib/server/naver";
import { session } from "@/lib/server/store";
import { loginDestination } from "@/lib/login-destination";
export const runtime = "nodejs";
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams,
    jar = await cookies();
  const saved = jar.get("career_naver_state")?.value,
    state = params.get("state"),
    destination = loginDestination(jar.get("career_naver_next")?.value);
  jar.set("career_naver_state", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth/naver",
    maxAge: 0,
  });
  jar.delete("career_naver_next");
  let config;
  try {
    config = naverConfig();
  } catch {}
  const base = config
    ? new URL(config.redirect).origin
    : new URL(request.url).origin;
  const fail = (error: string) =>
    Response.redirect(
      new URL(
        "/sign-in?" + new URLSearchParams({ error, next: destination }),
        base,
      ),
      303,
    );
  if (
    !saved ||
    !state ||
    !/^[a-f0-9]{64}$/.test(state) ||
    saved.length !== state.length ||
    !timingSafeEqual(Buffer.from(saved), Buffer.from(state))
  )
    return fail("naver_state");
  if (params.has("error")) return fail("naver_cancelled");
  const code = params.get("code");
  if (!code || code.length > 2000) return fail("naver_failed");
  try {
    const account = await naverIdentity(code, state);
    await session(account.id, account.password);
    return Response.redirect(new URL(destination, base), 303);
  } catch (error) {
    const reason = error instanceof Error ? error.message : "";
    return fail(
      reason === "ACCOUNT_LINK_REQUIRED"
        ? "naver_existing"
        : reason === "EMAIL_CONSENT_REQUIRED"
          ? "naver_email"
          : "naver_failed",
    );
  }
}
