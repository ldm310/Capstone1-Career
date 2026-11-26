import { z } from "zod";
import { user, isGuest } from "@/lib/server/store";
import { memberRole } from "@/lib/server/notices";
import { reviewDatabase } from "@/lib/server/extraction-review";
import { getExtractionReview } from "@/lib/server/extraction-review-queries";

export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store" };
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const current = await user();
    if (!current || isGuest(current.id))
      return Response.json(
        { error: "로그인이 필요합니다." },
        { status: 401, headers },
      );
    if ((await memberRole(current.id)) !== "ADMIN")
      return Response.json(
        { error: "관리자만 접근할 수 있습니다." },
        { status: 403, headers },
      );
    const input = z
      .string()
      .regex(/^[1-9]\d{0,18}$/)
      .refine((value) => value.length < 19 || value <= "9223372036854775807")
      .safeParse((await params).id);
    if (!input.success)
      return Response.json(
        { error: "검토 공고 번호를 확인해 주세요." },
        { status: 400, headers },
      );
    const detail = await getExtractionReview(reviewDatabase(), input.data);
    if (!detail)
      return Response.json(
        { error: "해당 검토 결과를 찾을 수 없습니다." },
        { status: 404, headers },
      );
    return Response.json(detail, { headers });
  } catch {
    return Response.json(
      { error: "원문과 추출 결과를 불러오지 못했습니다." },
      { status: 503, headers },
    );
  }
}
