import { z } from "zod";
import {
  user,
  isGuest,
  originCheck,
  jsonBody,
  rateLimit,
} from "@/lib/server/store";
import {
  verifiedEmail,
  requestEmailVerification,
  confirmEmailVerification,
} from "@/lib/server/email-verification";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store" };
export async function GET() {
  const current = await user();
  if (!current || isGuest(current.id))
    return Response.json(
      { error: "로그인이 필요합니다." },
      { status: 401, headers },
    );
  return Response.json(
    {
      email: current.email,
      verified: verifiedEmail(current.id, current.email),
    },
    { headers },
  );
}
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
    const body = z
      .discriminatedUnion("action", [
        z.object({ action: z.literal("request") }),
        z.object({
          action: z.literal("confirm"),
          token: z.string().regex(/^[a-f0-9]{64}$/),
        }),
      ])
      .parse(await jsonBody(request));
    if (body.action === "confirm") {
      rateLimit("email-verification:token:" + body.token.slice(0, 16), 10);
      await confirmEmailVerification(body.token);
      return Response.json({ ok: true }, { headers });
    }
    const current = await user();
    if (!current || isGuest(current.id))
      return Response.json(
        { error: "로그인이 필요합니다." },
        { status: 401, headers },
      );
    rateLimit("email-verification:request:" + current.id, 3);
    await requestEmailVerification(current.id);
    return Response.json({ ok: true }, { headers });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.startsWith("요청이 많습니다"))
      return Response.json({ error: message }, { status: 429, headers });
    if (message.startsWith("인증 링크") || message.startsWith("이메일이 변경"))
      return Response.json({ error: message }, { status: 400, headers });
    if (error instanceof z.ZodError)
      return Response.json(
        { error: "인증 요청을 확인해 주세요." },
        { status: 400, headers },
      );
    return Response.json(
      {
        error: "인증 메일을 보내지 못했습니다. 메일 발송 설정을 확인해 주세요.",
      },
      { status: 503, headers },
    );
  }
}
