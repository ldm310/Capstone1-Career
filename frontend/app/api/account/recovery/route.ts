import { after } from "next/server";
import { createHash } from "node:crypto";
import { z } from "zod";
import { originCheck, jsonBody, rateLimit } from "@/lib/server/store";
import { recoveryMailSettings } from "@/lib/server/recovery-mail";
import { requestPasswordRecovery } from "@/lib/server/password-recovery";
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
        email: z
          .string()
          .trim()
          .pipe(z.email("이메일 형식을 확인해 주세요.").max(200)),
      })
      .parse(await jsonBody(request));
    const email = input.email.toLowerCase();
    const ip =
      request.headers.get("x-real-ip") ||
      request.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim() ||
      "local";
    rateLimit(
      "recovery:ip:" + createHash("sha256").update(ip).digest("hex"),
      30,
    );
    rateLimit(
      "recovery:email:" + createHash("sha256").update(email).digest("hex"),
      5,
    );
    recoveryMailSettings();
    after(async () => {
      try {
        await requestPasswordRecovery(email);
      } catch (error) {
        console.error("Password recovery delivery failed", {
          name: error instanceof Error ? error.name : "UnknownError",
        });
      }
    });
    return Response.json(
      {
        ok: true,
        message:
          "가입된 이메일이라면 비밀번호 재설정 링크를 보냈습니다. 메일함을 확인해 주세요.",
      },
      { headers },
    );
  } catch (error) {
    if (error instanceof z.ZodError)
      return Response.json(
        { error: error.issues[0]?.message || "입력 내용을 확인해 주세요." },
        { status: 400, headers },
      );
    if (error instanceof Error && error.message.startsWith("요청이 많습니다"))
      return Response.json({ error: error.message }, { status: 429, headers });
    return Response.json(
      {
        error:
          "비밀번호 재설정 메일을 준비 중입니다. 잠시 후 다시 시도해 주세요.",
      },
      { status: 503, headers },
    );
  }
}
