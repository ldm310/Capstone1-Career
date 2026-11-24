import { z } from "zod";
import { createHash } from "node:crypto";
import { originCheck, jsonBody, rateLimit, logout } from "@/lib/server/store";
import { completePasswordRecovery } from "@/lib/server/password-recovery";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store" };
export async function POST(request: Request) {
  try {
    originCheck(request);
  } catch {
    return Response.json(
      { error: "요청 출처를 확인해 주세요." },
      { status: 403, headers },
    );
  }
  try {
    const input = z
      .object({
        token: z.string().regex(/^[a-f0-9]{64}$/),
        password: z.string().min(10).max(128),
        confirmation: z.string().max(128),
      })
      .parse(await jsonBody(request));
    const ip =
      request.headers.get("x-real-ip") ||
      request.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim() ||
      "local";
    rateLimit(
      "password-reset:ip:" + createHash("sha256").update(ip).digest("hex"),
      30,
    );
    if (input.password !== input.confirmation)
      return Response.json(
        { error: "비밀번호 확인이 일치하지 않습니다." },
        { status: 400, headers },
      );
    rateLimit("password-reset:" + input.token.slice(0, 16), 10);
    await completePasswordRecovery(input.token, input.password);
    await logout();
    return Response.json({ ok: true }, { headers });
  } catch {
    return Response.json(
      {
        error:
          "재설정 링크가 만료됐거나 올바르지 않습니다. 새 링크를 요청해 주세요. 비밀번호는 10자 이상 입력해 주세요.",
      },
      { status: 400, headers },
    );
  }
}
