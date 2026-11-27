import { z } from "zod";
import {
  user,
  isGuest,
  originCheck,
  jsonBody,
  rateLimit,
} from "@/lib/server/store";
import { memberRole } from "@/lib/server/notices";
import { reviewDatabase } from "@/lib/server/extraction-review";
import {
  listPostingPublication,
  changePostingPublication,
} from "@/lib/server/posting-publication";

export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store" };
const fail = (error: string, status: number) =>
  Response.json({ error }, { status, headers });
async function administrator() {
  const current = await user();
  if (!current || isGuest(current.id)) return null;
  return (await memberRole(current.id)) === "ADMIN" ? current : false;
}
export async function GET(request: Request) {
  try {
    const current = await administrator();
    if (!current)
      return fail(
        current === null
          ? "로그인이 필요합니다."
          : "관리자만 접근할 수 있습니다.",
        current === null ? 401 : 403,
      );
    const input = z
      .object({
        status: z
          .enum(["PUBLISHED", "HIDDEN", "FILTERED", "CLOSED"])
          .default("PUBLISHED"),
        q: z.string().trim().max(100).default(""),
        offset: z.coerce.number().int().min(0).max(100000).default(0),
      })
      .safeParse(Object.fromEntries(new URL(request.url).searchParams));
    if (!input.success) return fail("조회 조건을 확인해 주세요.", 400);
    return Response.json(
      await listPostingPublication(
        reviewDatabase(),
        input.data.status,
        input.data.q,
        input.data.offset,
      ),
      { headers },
    );
  } catch {
    return fail("공고 노출 관리 목록을 불러오지 못했습니다.", 503);
  }
}
export async function PATCH(request: Request) {
  try {
    const current = await administrator();
    if (!current)
      return fail(
        current === null
          ? "로그인이 필요합니다."
          : "관리자만 처리할 수 있습니다.",
        current === null ? 401 : 403,
      );
    try {
      originCheck(request);
    } catch {
      return fail("요청 출처를 확인해 주세요.", 403);
    }
    rateLimit("posting-publication:" + current.id, 60);
    const input = z
      .object({
        id: z.string().regex(/^[1-9]\d{0,18}$/),
        revision: z.number().int().min(0).max(2147483646),
        hidden: z.boolean(),
      })
      .safeParse(await jsonBody(request));
    if (!input.success) return fail("처리 내용을 확인해 주세요.", 400);
    if (
      !(await changePostingPublication(
        reviewDatabase(),
        input.data,
        current.id,
      ))
    )
      return fail(
        "상태가 변경됐거나 다시 올릴 수 없는 공고입니다. 목록을 새로고침해 주세요.",
        409,
      );
    return Response.json({ ok: true }, { headers });
  } catch {
    return fail("공고 노출 상태를 저장하지 못했습니다.", 503);
  }
}
