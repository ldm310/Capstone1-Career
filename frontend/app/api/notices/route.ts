import { randomUUID } from "node:crypto";
import { z } from "zod";
import {
  user,
  isGuest,
  originCheck,
  jsonBody,
  rateLimit,
} from "@/lib/server/store";
import {
  memberRole,
  noticeDatabase,
  noticeColumns,
  profileNamespace,
} from "@/lib/server/notices";

export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store" };
const input = z.object({
  title: z.string().trim().min(1).max(120),
  content: z.string().trim().min(1).max(12000),
  pinned: z.boolean().default(false),
});
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const offset = Number(params.get("offset") || 0);
  if (!Number.isInteger(offset) || offset < 0 || offset > 10000)
    return Response.json(
      { error: "페이지를 확인해 주세요." },
      { status: 400, headers },
    );
  try {
    const current = await user();
    const canManage =
      !!current &&
      !isGuest(current.id) &&
      (await memberRole(current.id)) === "ADMIN";
    const db = noticeDatabase();
    const rows = await db.query(
      `SELECT ${noticeColumns} FROM public.career_notice WHERE namespace=$1 AND deleted_at IS NULL ORDER BY pinned DESC,created_at DESC,id LIMIT 21 OFFSET $2`,
      [profileNamespace(), offset],
    );
    return Response.json(
      {
        notices: rows.rows.slice(0, 20),
        nextOffset: rows.rows.length > 20 ? offset + 20 : null,
        canManage,
      },
      { headers },
    );
  } catch {
    return Response.json(
      { error: "공지사항을 불러오지 못했습니다." },
      { status: 503, headers },
    );
  }
}
async function change(request: Request, method: "POST" | "PATCH" | "DELETE") {
  const current = await user();
  if (!current || isGuest(current.id))
    return Response.json(
      { error: "로그인이 필요합니다." },
      { status: 401, headers },
    );
  try {
    originCheck(request);
  } catch {
    return Response.json(
      { error: "요청 출처를 확인해 주세요." },
      { status: 403, headers },
    );
  }
  try {
    if ((await memberRole(current.id)) !== "ADMIN")
      return Response.json(
        { error: "관리자만 공지사항을 작성할 수 있습니다." },
        { status: 403, headers },
      );
    rateLimit("notices:" + current.id, 60);
    const body = await jsonBody(request);
    const id =
      method === "POST"
        ? randomUUID()
        : z.string().min(1).max(160).parse(body.id);
    const db = noticeDatabase(),
      namespace = profileNamespace();
    if (method === "DELETE") {
      const result = await db.query(
        `UPDATE public.career_notice SET deleted_at=now(),updated_at=now() WHERE namespace=$1 AND id=$2 AND deleted_at IS NULL RETURNING id`,
        [namespace, id],
      );
      return Response.json(
        result.rowCount ? { ok: true } : { error: "공지를 찾을 수 없습니다." },
        { status: result.rowCount ? 200 : 404, headers },
      );
    }
    const data = input.parse(body);
    const result =
      method === "POST"
        ? await db.query(
            `INSERT INTO public.career_notice(namespace,id,title,content,pinned,author_id,author_name) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING ${noticeColumns}`,
            [
              namespace,
              id,
              data.title,
              data.content,
              data.pinned,
              current.id,
              current.name,
            ],
          )
        : await db.query(
            `UPDATE public.career_notice SET title=$3,content=$4,pinned=$5,updated_at=now() WHERE namespace=$1 AND id=$2 AND deleted_at IS NULL RETURNING ${noticeColumns}`,
            [namespace, id, data.title, data.content, data.pinned],
          );
    return Response.json(
      result.rowCount
        ? { notice: result.rows[0] }
        : { error: "공지를 찾을 수 없습니다." },
      {
        status: result.rowCount ? (method === "POST" ? 201 : 200) : 404,
        headers,
      },
    );
  } catch (error) {
    return Response.json(
      {
        error:
          error instanceof z.ZodError
            ? "제목과 내용을 확인해 주세요."
            : "공지사항을 저장하지 못했습니다.",
      },
      { status: error instanceof z.ZodError ? 400 : 503, headers },
    );
  }
}
export const POST = (request: Request) => change(request, "POST");
export const PATCH = (request: Request) => change(request, "PATCH");
export const DELETE = (request: Request) => change(request, "DELETE");
