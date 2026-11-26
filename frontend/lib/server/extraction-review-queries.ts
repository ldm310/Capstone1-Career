import type { Pool, PoolClient } from "pg";
import { koreaTodaySql } from "./posting-metadata-sql";
import type {
  ExtractionReviewDetail,
  ReviewItem,
} from "@/types/extraction-review";

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
  CASE WHEN p.site IN ('사람인','saramin') AND p.site_posting_no ~ '^[0-9]+$'
    THEN 'https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=' || p.site_posting_no
    ELSE '' END AS "sourceUrl",
  p.deadline,coalesce(p.deadline<${koreaTodaySql},false) AS "deadlinePassed",p.status='마감' AS "sourceClosed",
  ${statusSql} AS status, e.review_result AS "reviewResult",
  coalesce(e.review_feedback,'') AS feedback, e.review_reasons AS "reviewReasons",
  coalesce(e.reviewed_at,e.run_at) AS "updatedAt", ${revisionSql} AS revision`;

export async function getExtractionReview(
  db: Database,
  id: string,
): Promise<ExtractionReviewDetail | null> {
  // Read the requested run, including non-target units: reviewers must see
  // exactly what the LLM returned and what the pipeline stored before deciding.
  const { rows } = await db.query(
    `SELECT ${columnsSql},p.id::text AS "postingId",p.body_html AS "bodyHtml",p.last_checked_at AS "lastCheckedAt",
    e.is_current AS "isCurrent",e.model,e.prompt_version AS "promptVersion",e.dict_version AS "dictVersion",e.run_at AS "runAt",e.llm_output_raw AS "rawOutput",
    coalesce((SELECT jsonb_agg(jsonb_build_object('seq',im.seq,'url',im.url,'kept',im.kept) ORDER BY im.seq,im.id)
      FROM public.posting_image im WHERE im.posting_id=p.id),'[]'::jsonb) AS images,
    coalesce((SELECT jsonb_agg(jsonb_build_object('id',u.id::text,'name',u.name,'isIt',u.is_it,'job',u.job,'career',u.career,'years',u.years_text,
      'items',coalesce((SELECT jsonb_agg(jsonb_build_object('category',i.category,'text',i.text,'quote',i.quote) ORDER BY i.seq,i.id)
        FROM public.unit_item i WHERE i.unit_id=u.id),'[]'::jsonb)) ORDER BY u.seq,u.id)
      FROM public.recruit_unit u WHERE u.run_id=e.id),'[]'::jsonb) AS units
    ${fromSql} WHERE e.id=$1 AND jsonb_array_length(e.review_reasons)>0`,
    [id],
  );
  if (!rows[0]) return null;
  const row = rows[0];
  const review: ReviewItem = {
    id: row.id,
    postingNo: row.postingNo,
    site: row.site,
    company: row.company,
    title: row.title,
    sourceUrl: row.sourceUrl,
    status: row.status,
    feedback: row.feedback,
    updatedAt: row.updatedAt,
    revision: row.revision,
    reviewReasons: row.reviewReasons,
    deadline: row.deadline,
    deadlinePassed: row.deadlinePassed,
    sourceClosed: row.sourceClosed,
  };
  return {
    review,
    posting: {
      id: row.postingId,
      bodyHtml: row.bodyHtml,
      lastCheckedAt: row.lastCheckedAt,
      images: row.images,
    },
    extraction: {
      id: row.id,
      isCurrent: row.isCurrent,
      model: row.model,
      promptVersion: row.promptVersion,
      dictVersion: row.dictVersion,
      runAt: row.runAt,
      rawOutput: row.rawOutput,
      units: row.units,
    },
  };
}

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
    expiredOpenCount: (
      await db.query(
        `SELECT count(*)::int AS n ${fromSql} WHERE ${candidatesSql} AND e.review_result IS NULL AND p.deadline<${koreaTodaySql}`,
      )
    ).rows[0].n as number,
  };
}

export async function decideExtractionReview(
  db: Database,
  input: {
    id: string;
    revision: string;
    action: "PASS" | "RETRY" | "APPROVE" | "RESTORE";
    feedback: string;
  },
): Promise<"saved" | "missing" | "conflict"> {
  // Conditional UPDATE protects against another reviewer or a new pipeline result.
  // The team role updates exactly these three columns, without an auxiliary table.
  const restore = input.action === "RESTORE";
  const saved = await db.query(
    `UPDATE public.extraction_run e SET review_result=$2,review_feedback=CASE WHEN $5='RESTORE' THEN '검토 대기 복원: '||clock_timestamp()::text WHEN $5='PASS' AND p.deadline<${koreaTodaySql} THEN '마감일 경과로 넘김' ELSE $3 END,reviewed_at=CASE WHEN $5='RESTORE' THEN NULL ELSE clock_timestamp() END
     FROM public.posting p WHERE e.id=$1 AND p.id=e.posting_id AND e.is_current
       AND (CASE WHEN $5='RESTORE' THEN e.review_result IS NOT NULL ELSE e.review_result IS NULL END)
       AND ($5 IN ('PASS','RESTORE') OR (p.status='진행' AND (p.deadline IS NULL OR p.deadline>=${koreaTodaySql})))
       AND jsonb_array_length(e.review_reasons)>0 AND ${revisionSql}=$4
     RETURNING e.id`,
    [
      input.id,
      restore
        ? null
        : input.action === "PASS"
          ? "제외"
          : input.action === "APPROVE"
            ? "정상"
            : "다시",
      input.action === "RETRY" ? input.feedback : null,
      input.revision,
      input.action,
    ],
  );
  if (saved.rowCount) return "saved";
  const exists = await db.query(
    "SELECT id FROM public.extraction_run WHERE id=$1 AND jsonb_array_length(review_reasons)>0",
    [input.id],
  );
  return exists.rowCount ? "conflict" : "missing";
}

export async function passExpiredExtractionReviews(db: Database) {
  const result =
    await db.query(`UPDATE public.extraction_run e SET review_result='제외',review_feedback='마감일 경과로 넘김',reviewed_at=clock_timestamp()
   FROM public.posting p WHERE p.id=e.posting_id AND e.is_current AND e.review_result IS NULL
     AND jsonb_array_length(e.review_reasons)>0 AND p.deadline<${koreaTodaySql} RETURNING e.id::text`);
  return result.rowCount || 0;
}
