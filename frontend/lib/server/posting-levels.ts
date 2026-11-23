import "server-only";
import { Pool } from "pg";
import { readFileSync } from "node:fs";
import type { PostingLevels } from "@/types/posting-level";

const shared = globalThis as unknown as { careerLevelPool?: Pool };
export function profilePool() {
  if (!process.env.CAREER_PROFILE_DATABASE_URL) return null;
  return (shared.careerLevelPool ??= new Pool({
    connectionString: process.env.CAREER_PROFILE_DATABASE_URL,
    ssl: process.env.CAREER_PROFILE_CA_FILE
      ? {
          ca: readFileSync(process.env.CAREER_PROFILE_CA_FILE, "utf8"),
          rejectUnauthorized: true,
        }
      : undefined,
    max: 3,
    connectionTimeoutMillis: 5000,
    idleTimeoutMillis: 10000,
    statement_timeout: 5000,
  }));
}

// The caller supplies only the authenticated session subject, never a query userId.
export async function postingLevels(
  subject: string,
  jobId: string,
  version: string,
): Promise<PostingLevels | null> {
  const connection = profilePool();
  if (!connection) return null;
  const namespace = process.env.CAREER_PROFILE_NAMESPACE || "local-review";
  const { rows } = await connection.query(
    `
    SELECT keyword_id AS "keywordId", keyword_text AS text,
      category_codes AS "categoryCodes", score,
      reference_score AS "referenceScore", reference_kind AS "referenceKind",
      evaluation_kind AS "evaluationKind", evaluated_at AS "evaluatedAt"
    FROM public.career_lv_posting_keyword_level l
    WHERE namespace=$1 AND subject_id=$2 AND job_id=$3 AND taxonomy_version=$4
      AND (evaluation_kind='CONFIRMED' OR
        (evaluation_kind='DEMO' AND EXISTS (
          SELECT 1 FROM public.career_lv_member m
          WHERE m.namespace=l.namespace AND m.subject_id=l.subject_id
            AND ((l.subject_id='demo-user' AND m.is_demo)
              OR (m.preview_enabled AND l.method_version='preview-fixture-v1')))))
    ORDER BY keyword_id`,
    [namespace, subject, jobId, version],
  );
  const sources = await connection.query(
    `SELECT source_id AS id, kind, title, is_simulated AS simulated
    FROM public.career_lv_analysis_source WHERE namespace=$1 AND subject_id=$2 ORDER BY source_id`,
    [namespace, subject],
  );
  return {
    jobId,
    taxonomyVersion: version,
    source: "RDS",
    levels: rows,
    sources: sources.rows,
  };
}
