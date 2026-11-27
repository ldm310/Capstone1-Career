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
  listExtractionReviews,
  decideExtractionReview,
  passExpiredExtractionReviews,
} from "@/lib/server/extraction-review-queries";

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
          .enum(["OPEN", "SKIPPED", "RETRY_REQUESTED", "RESOLVED", "ALL"])
          .default("OPEN"),
        q: z.string().trim().max(100).default(""),
        offset: z.coerce.number().int().min(0).max(100000).default(0),
      })
      .safeParse(Object.fromEntries(new URL(request.url).searchParams));
    if (!input.success) return fail("조회 조건을 확인해 주세요.", 400);
    const { status, q, offset } = input.data;
    return Response.json(
      await listExtractionReviews(reviewDatabase(), status, q, offset),
      { headers },
    );
  } catch {
    return fail("추출 검토 목록을 불러오지 못했습니다.", 503);
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
    rateLimit("extraction-review:" + current.id, 60);
    const input = z
      .object({
        id: z.string().regex(/^\d{1,19}$/),
        revision: z.string().regex(/^[a-f0-9]{32}$/),
        action: z.enum(["PASS", "RETRY", "APPROVE", "RESTORE"]),
        feedback: z.string().trim().max(2000).default(""),
      })
      .safeParse(await jsonBody(request));
    if (!input.success) return fail("처리 내용을 확인해 주세요.", 400);
    if (input.data.action === "RETRY" && input.data.feedback.length < 5)
      return fail("재추출 피드백을 5자 이상 입력해 주세요.", 400);
    const result = await decideExtractionReview(reviewDatabase(), input.data);
    if (result === "missing")
      return fail("해당 추출 결과를 찾을 수 없습니다.", 404);
    if (result === "conflict")
      return fail(
        "공고가 마감됐거나 이미 검토 또는 재추출됐습니다. 목록을 새로고침해 주세요.",
        409,
      );
    return Response.json(
      {
        ok: true,
        status: {
          PASS: "SKIPPED",
          RETRY: "RETRY_REQUESTED",
          APPROVE: "RESOLVED",
          RESTORE: "OPEN",
        }[input.data.action],
      },
      { headers },
    );
  } catch {
    return fail("처리 내용을 저장하지 못했습니다.", 503);
  }
}

export async function POST(request: Request) {
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
    const input = z
      .object({ action: z.literal("PASS_EXPIRED") })
      .safeParse(await jsonBody(request));
    if (!input.success) return fail("처리 내용을 확인해 주세요.", 400);
    rateLimit("extraction-review:" + current.id, 60);
    return Response.json(
      {
        ok: true,
        updated: await passExpiredExtractionReviews(reviewDatabase()),
      },
      { headers },
    );
  } catch {
    return fail("마감 공고를 넘김 처리하지 못했습니다.", 503);
  }
}
