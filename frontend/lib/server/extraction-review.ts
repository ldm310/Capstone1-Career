import "server-only";
import { profilePool } from "./posting-levels";

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
  last_failed_at AS "lastFailedAt",updated_at AS "updatedAt",revision`;
