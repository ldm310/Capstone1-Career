import type { Pool, PoolClient } from "pg";

type Database = Pick<Pool | PoolClient, "query">;
export type ReviewStatus = "OPEN" | "SKIPPED" | "RETRY_REQUESTED" | "RESOLVED";
const statusSql = `CASE e.review_result WHEN '제외' THEN 'SKIPPED'
  WHEN '다시' THEN 'RETRY_REQUESTED' WHEN '정상' THEN 'RESOLVED' ELSE 'OPEN' END`;
const revisionSql = `md5(jsonb_build_array(e.review_result,e.review_feedback,e.reviewed_at)::text)`;
const fromSql = `FROM public.extraction_run e
  JOIN public.posting p ON p.id=e.posting_id
  JOIN public.company c ON c.id=p.company_id`;
const candidatesSql = `e.is_current AND jsonb_array_length(e.review_reasons)>0`;
const columnsSql = `e.id::text, p.site, p.site_posting_no AS "postingNo", c.name AS company, p.title,
  CASE WHEN p.site='사람인' AND p.site_posting_no ~ '^[0-9]+$'
    THEN 'https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=' || p.site_posting_no
    ELSE '' END AS "sourceUrl",
  ${statusSql} AS status, e.review_result AS "reviewResult",
  coalesce(e.review_feedback,'') AS feedback, e.review_reasons AS "reviewReasons",
  coalesce(e.reviewed_at,e.run_at) AS "updatedAt", ${revisionSql} AS revision`;

export async function listExtractionReviews(
  db: Database,
  status: ReviewStatus | "ALL",
  query: string,
  offset: number,
) {
  const filter = `${candidatesSql} AND ($1='ALL' OR (${statusSql})=$1)
    AND ($2='' OR c.name ILIKE $3 OR p.title ILIKE $3 OR p.site_posting_no ILIKE $3)`;
  const values = [status, query, `%${query}%`];
  const rows = await db.query(
    `SELECT ${columnsSql} ${fromSql} WHERE ${filter}
     ORDER BY coalesce(e.reviewed_at,e.run_at) DESC,e.id DESC LIMIT 21 OFFSET $4`,
    [...values, offset],
  );
  const total = await db.query(
    `SELECT count(*)::int AS count ${fromSql} WHERE ${filter}`,
    values,
  );
  const counts = await db.query(
    `SELECT ${statusSql} AS status,count(*)::int AS count ${fromSql}
     WHERE ${candidatesSql} GROUP BY e.review_result`,
  );
  const latest = await db.query(
    "SELECT max(run_at) AS seen FROM public.extraction_run",
  );
  return {
    storage: "extraction_run" as const,
    items: rows.rows.slice(0, 20),
    total: total.rows[0].count as number,
    nextOffset: rows.rows.length > 20 ? offset + 20 : null,
    counts: Object.fromEntries(
      counts.rows.map((row) => [row.status, row.count]),
    ),
    lastPipelineAt: latest.rows[0].seen,
  };
}

export async function decideExtractionReview(
  db: Database,
  input: {
    id: string;
    revision: string;
    action: "PASS" | "RETRY";
    feedback: string;
  },
): Promise<"saved" | "missing" | "conflict"> {
  // Conditional UPDATE protects against another reviewer or a new pipeline result.
  // The team role updates exactly these three columns, without an auxiliary table.
  const saved = await db.query(
    `UPDATE public.extraction_run e SET review_result=$2,review_feedback=$3,reviewed_at=clock_timestamp()
     WHERE e.id=$1 AND e.is_current AND e.review_result IS NULL
       AND jsonb_array_length(e.review_reasons)>0 AND ${revisionSql}=$4
     RETURNING e.id`,
    [
      input.id,
      input.action === "PASS" ? "제외" : "다시",
      input.action === "RETRY" ? input.feedback : null,
      input.revision,
    ],
  );
  if (saved.rowCount) return "saved";
  const exists = await db.query(
    "SELECT id FROM public.extraction_run WHERE id=$1 AND jsonb_array_length(review_reasons)>0",
    [input.id],
  );
  return exists.rowCount ? "conflict" : "missing";
}
