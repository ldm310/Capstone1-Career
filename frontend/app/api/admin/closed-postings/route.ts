import { z } from "zod";
import { user, isGuest } from "@/lib/server/store";
import { memberRole } from "@/lib/server/notices";
import { profilePool } from "@/lib/server/posting-levels";
import { closedPostingSql } from "@/lib/server/posting-metadata-sql";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store" };
export async function GET(request: Request) {
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
      .object({
        q: z.string().trim().max(100).default(""),
        offset: z.coerce.number().int().min(0).max(100000).default(0),
      })
      .safeParse(Object.fromEntries(new URL(request.url).searchParams));
    if (!input.success)
      return Response.json(
        { error: "조회 조건을 확인해 주세요." },
        { status: 400, headers },
      );
    const pool = profilePool();
    if (!pool) throw new Error("Database unavailable");
    const { rows } = await pool.query(
      `WITH closed AS (
      SELECT p.id::text AS id,c.name AS company,p.title,p.site,p.site_posting_no AS "postingNo",p.deadline,
        CASE WHEN p.deadline < (now() AT TIME ZONE 'Asia/Seoul')::date THEN '마감일 경과' ELSE '원문 마감' END AS reason,
        CASE WHEN p.site IN ('사람인','saramin') AND p.site_posting_no ~ '^[0-9]+$' THEN 'https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx='||p.site_posting_no ELSE '' END AS "sourceUrl"
      FROM public.posting p JOIN public.company c ON c.id=p.company_id WHERE ${closedPostingSql("p")}
        AND ($1='' OR strpos(lower(c.name||' '||p.title||' '||p.site_posting_no),lower($1))>0)
    ) SELECT (SELECT count(*)::int FROM closed) AS total,coalesce((SELECT jsonb_agg(row_to_json(page)) FROM (SELECT * FROM closed ORDER BY deadline DESC NULLS LAST,id::bigint DESC LIMIT 20 OFFSET $2) page),'[]'::jsonb) AS items`,
      [input.data.q, input.data.offset],
    );
    return Response.json(rows[0], { headers });
  } catch {
    return Response.json(
      { error: "마감 공고를 불러오지 못했습니다." },
      { status: 503, headers },
    );
  }
}
