import { randomUUID } from "node:crypto";
import { z } from "zod";
import {
  user,
  isGuest,
  originCheck,
  jsonBody,
  rateLimit,
} from "@/lib/server/store";
import { memberRole } from "@/lib/server/notices";
import {
  reviewColumns,
  reviewDatabase,
  reviewNamespace,
} from "@/lib/server/extraction-review";
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
    const params = new URL(request.url).searchParams;
    const input = z
      .object({
        status: z
          .enum([
            "OPEN",
            "SKIPPED",
            "RETRY_REQUESTED",
            "RUNNING",
            "RESOLVED",
            "ALL",
          ])
          .default("OPEN"),
        q: z.string().trim().max(100).default(""),
        offset: z.coerce.number().int().min(0).max(100000).default(0),
      })
      .safeParse(Object.fromEntries(params));
    if (!input.success) return fail("조회 조건을 확인해 주세요.", 400);
    const { status, q, offset } = input.data;
    const db = reviewDatabase(),
      namespace = reviewNamespace();
    const rows = await db.query(
      `SELECT ${reviewColumns} FROM public.career_extraction_review
      WHERE namespace=$1 AND ($2='ALL' OR status=$2) AND ($3='' OR company ILIKE $4 OR title ILIKE $4 OR posting_no ILIKE $4)
      ORDER BY updated_at DESC,id DESC LIMIT 21 OFFSET $5`,
      [namespace, status, q, `%${q}%`, offset],
    );
    const counts = await db.query(
      "SELECT status,count(*)::int AS count FROM public.career_extraction_review WHERE namespace=$1 GROUP BY status",
      [namespace],
    );
    const worker = await db.query(
      "SELECT max(e.created_at) AS seen FROM public.career_extraction_review_event e JOIN public.career_extraction_review r ON r.id=e.review_id WHERE r.namespace=$1 AND e.action='START'",
      [namespace],
    );
    return Response.json(
      {
        items: rows.rows.slice(0, 20),
        nextOffset: rows.rows.length > 20 ? offset + 20 : null,
        counts: Object.fromEntries(
          counts.rows.map((row) => [row.status, row.count]),
        ),
        lastPipelineAt: worker.rows[0].seen,
      },
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
        id: z.string().regex(/^\d{1,20}$/),
        revision: z.number().int().min(0),
        action: z.enum(["PASS", "RETRY"]),
        feedback: z.string().trim().max(2000).default(""),
      })
      .safeParse(await jsonBody(request));
    if (!input.success) return fail("처리 내용을 확인해 주세요.", 400);
    const { id, revision, action, feedback } = input.data;
    if (action === "RETRY" && feedback.length < 5)
      return fail("재추출 피드백을 5자 이상 입력해 주세요.", 400);
    const connection = await reviewDatabase().connect();
    try {
      await connection.query("BEGIN");
      const selected = await connection.query(
        "SELECT status,revision FROM public.career_extraction_review WHERE namespace=$1 AND id=$2 FOR UPDATE",
        [reviewNamespace(), id],
      );
      const row = selected.rows[0];
      if (!row) {
        await connection.query("ROLLBACK");
        return fail("해당 공고를 찾을 수 없습니다.", 404);
      }
      if (
        row.revision !== revision ||
        ["RUNNING", "RESOLVED"].includes(row.status)
      ) {
        await connection.query("ROLLBACK");
        return fail("처리 상태가 바뀌었습니다. 목록을 새로고침해 주세요.", 409);
      }
      const status = action === "PASS" ? "SKIPPED" : "RETRY_REQUESTED";
      await connection.query(
        `UPDATE public.career_extraction_review SET status=$3,feedback=$4,actor_name=$5,request_id=$6,revision=revision+1,updated_at=now() WHERE namespace=$1 AND id=$2`,
        [
          reviewNamespace(),
          id,
          status,
          feedback,
          current.name,
          action === "RETRY" ? randomUUID() : null,
        ],
      );
      await connection.query(
        "INSERT INTO public.career_extraction_review_event(id,review_id,action,feedback,actor_id,actor_name) VALUES($1,$2,$3,$4,$5,$6)",
        [randomUUID(), id, action, feedback, current.id, current.name],
      );
      await connection.query("COMMIT");
      return Response.json({ ok: true, status }, { headers });
    } catch (error) {
      await connection.query("ROLLBACK");
      throw error;
    } finally {
      connection.release();
    }
  } catch {
    return fail("처리 내용을 저장하지 못했습니다.", 503);
  }
}
