import "server-only";
import { profilePool } from "./posting-levels";
import { readFileSync } from "node:fs";
import path from "node:path";

export const reviewNamespace = () =>
  process.env.CAREER_PIPELINE_NAMESPACE ||
  process.env.CAREER_PROFILE_NAMESPACE ||
  "local-review";
export function reviewDatabase() {
  const pool = profilePool();
  if (!pool) throw new Error("EXTRACTION_REVIEW_UNAVAILABLE");
  return pool;
}
export const reviewColumns = `id::text,site,posting_no AS "postingNo",company,title,source_url AS "sourceUrl",
  stage,error_code AS "errorCode",failure_count AS "failureCount",status,feedback,actor_name AS "actorName",
  last_failed_at AS "lastFailedAt",updated_at AS "updatedAt",revision,review_reasons AS "reviewReasons",source_run_id::text AS "sourceRunId"`;

export async function syncReviewCandidates() {
  const db = reviewDatabase(),
    namespace = reviewNamespace();
  await db.query(
    readFileSync(
      path.resolve(process.cwd(), "../job-skill/db/sync_extraction_review.sql"),
      "utf8",
    ),
    [namespace],
  );
  await db.query(
    `UPDATE public.career_extraction_review r SET status='RESOLVED',revision=revision+1,updated_at=now()
    WHERE namespace=$1 AND stage='REVIEW' AND source_run_id IS NOT NULL AND status='OPEN'
      AND NOT EXISTS(SELECT 1 FROM public.career_extraction_review_candidates c WHERE c.site=r.site AND c.posting_no=r.posting_no)`,
    [namespace],
  );
}
