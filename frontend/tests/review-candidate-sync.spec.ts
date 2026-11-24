import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { loadEnvConfig } from "@next/env";
import { Client } from "pg";

test("review candidates exclude missing results and preserve decisions for the same run", async () => {
  test.skip(
    process.env.RUN_RDS_ADMIN_REVIEW_TESTS !== "1",
    "Explicit RDS integration opt-in",
  );
  loadEnvConfig(process.cwd(), false, { info() {}, error() {} });
  const db = new Client({
    connectionString: process.env.CAREER_PROFILE_DATABASE_URL,
    ssl: {
      ca: readFileSync(process.env.CAREER_PROFILE_CA_FILE!, "utf8"),
      rejectUnauthorized: true,
    },
    connectionTimeoutMillis: 5000,
  });
  const namespace = "review-sync-test-" + randomUUID();
  const sql = readFileSync(
    "../job-skill/db/sync_extraction_review.sql",
    "utf8",
  );
  await db.connect();
  try {
    const source = await db.query(
      "SELECT count(*)::int AS count FROM public.career_extraction_review_candidates",
    );
    expect(source.rows[0].count).toBeGreaterThan(0);
    const wrong =
      await db.query(`SELECT count(*)::int AS count FROM public.career_extraction_review_candidates c
      WHERE NOT EXISTS(SELECT 1 FROM public.extraction_run e WHERE e.id=c.source_run_id AND e.is_current AND e.review_result IS NULL AND jsonb_array_length(e.review_reasons)>0)`);
    expect(wrong.rows[0].count).toBe(0);
    await db.query(sql, [namespace]);
    const initial = await db.query(
      "SELECT id::text,source_run_id::text,revision FROM public.career_extraction_review WHERE namespace=$1 ORDER BY id",
      [namespace],
    );
    expect(initial.rowCount).toBe(source.rows[0].count);
    const first = initial.rows[0];
    await db.query(
      "UPDATE public.career_extraction_review SET status='SKIPPED',feedback='관리자가 확인한 결과 유지' WHERE namespace=$1 AND id=$2",
      [namespace, first.id],
    );
    await db.query(sql, [namespace]);
    let row = (
      await db.query(
        "SELECT status,feedback,revision FROM public.career_extraction_review WHERE namespace=$1 AND id=$2",
        [namespace, first.id],
      )
    ).rows[0];
    expect(row.status).toBe("SKIPPED");
    expect(row.feedback).toBe("관리자가 확인한 결과 유지");
    expect(row.revision).toBe(first.revision);
    // Simulate an older source pointer on only the isolated queue row, never modify the real extraction.
    await db.query(
      "UPDATE public.career_extraction_review SET source_run_id=-1 WHERE namespace=$1 AND id=$2",
      [namespace, first.id],
    );
    await db.query(sql, [namespace]);
    row = (
      await db.query(
        "SELECT status,source_run_id::text,feedback FROM public.career_extraction_review WHERE namespace=$1 AND id=$2",
        [namespace, first.id],
      )
    ).rows[0];
    expect(row.status).toBe("OPEN");
    expect(row.source_run_id).toBe(first.source_run_id);
    expect(row.feedback).toBe("관리자가 확인한 결과 유지");
  } finally {
    await db.query(
      "DELETE FROM public.career_extraction_review WHERE namespace=$1",
      [namespace],
    );
    await db.end();
  }
});
