import { test, expect } from "@playwright/test";
import { Client } from "pg";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  listExtractionReviews,
  decideExtractionReview,
} from "../lib/server/extraction-review-queries";

test("review queries use only extraction_run and the three granted update columns", async () => {
  const url = process.env.TEST_DATABASE_URL;
  if (process.env.REQUIRE_REVIEW_DB === "1") expect(url).toBeTruthy();
  test.skip(!url, "A local isolated PostgreSQL is required");
  const parsed = new URL(url!);
  expect(["127.0.0.1", "localhost", "[::1]"]).toContain(parsed.hostname);
  const name = "career_review_test_" + randomUUID().replaceAll("-", "");
  const role = name + "_role";
  const admin = new Client({ connectionString: url });
  let db: Client | undefined;
  let reader: Client | undefined;
  let contender: Client | undefined;
  await admin.connect();
  try {
    await admin.query(`CREATE DATABASE "${name}"`);
    await admin.query(`CREATE ROLE "${role}" NOLOGIN`);
    parsed.pathname = "/" + name;
    db = new Client({ connectionString: parsed.href });
    await db.connect();
    await db.query(
      readFileSync(path.resolve("../job-skill/db/schema.sql"), "utf8"),
    );
    const company = (
      await db.query(
        "INSERT INTO company(name) VALUES('검증 기업') RETURNING id",
      )
    ).rows[0].id;
    const ids: string[] = [];
    const reason = JSON.stringify([
      { 검사: 2, 내용: "모집 직무 칸 3개 / 만든 자리 이름 1개" },
    ]);
    for (let i = 0; i < 27; i++) {
      const posting = (
        await db.query(
          "INSERT INTO posting(company_id,site_posting_no,title,kind,raw_hash) VALUES($1,$2,$3,'글',$4) RETURNING id",
          [company, String(55000000 + i), `검증 공고 ${i}`, "a".repeat(64)],
        )
      ).rows[0].id;
      const run = (
        await db.query(
          `INSERT INTO extraction_run(posting_id,model,prompt_version,dict_version,input_hash,input_tokens,output_tokens,cost_usd,is_current,review_reasons)
         VALUES($1,'test','test','test',$2,0,0,0,true,$3) RETURNING id::text`,
          [posting, "b".repeat(64), reason],
        )
      ).rows[0].id;
      ids.push(run);
    }
    await db.query(`GRANT USAGE ON SCHEMA public TO "${role}"`);
    await db.query(
      `GRANT SELECT ON company,posting,extraction_run TO "${role}"`,
    );
    await db.query(
      `GRANT UPDATE(review_result,review_feedback,reviewed_at) ON extraction_run TO "${role}"`,
    );
    reader = new Client({ connectionString: parsed.href });
    await reader.connect();
    await reader.query(`SET ROLE "${role}"`);
    const first = await listExtractionReviews(reader, "OPEN", "", 0);
    expect(first.storage).toBe("extraction_run");
    expect(first.total).toBe(27);
    expect(first.items).toHaveLength(20);
    expect(first.nextOffset).toBe(20);
    expect(first.counts.OPEN).toBe(27);
    expect(
      (await listExtractionReviews(reader, "OPEN", "", 20)).items,
    ).toHaveLength(7);
    const selected = await listExtractionReviews(reader, "OPEN", "55000000", 0);
    expect(selected.total).toBe(1);
    expect(selected.items[0].id).toBe(ids[0]);
    expect(selected.items[0].sourceUrl).toContain("rec_idx=55000000");
    const token = selected.items[0].revision;
    const unchanged = (
      await db.query(
        "SELECT model,input_hash,is_current,review_reasons FROM extraction_run WHERE id=$1",
        [ids[0]],
      )
    ).rows[0];
    expect(
      await decideExtractionReview(reader, {
        id: ids[0],
        revision: token,
        action: "PASS",
        feedback: "",
      }),
    ).toBe("saved");
    const pass = (
      await db.query(
        "SELECT review_result,review_feedback,reviewed_at FROM extraction_run WHERE id=$1",
        [ids[0]],
      )
    ).rows[0];
    expect(pass.review_result).toBe("제외");
    expect(pass.review_feedback).toBeNull();
    expect(pass.reviewed_at).toBeTruthy();
    expect(
      (
        await db.query(
          "SELECT model,input_hash,is_current,review_reasons FROM extraction_run WHERE id=$1",
          [ids[0]],
        )
      ).rows[0],
    ).toEqual(unchanged);
    expect(
      await decideExtractionReview(reader, {
        id: ids[0],
        revision: token,
        action: "RETRY",
        feedback: "덮어쓰면 안 됨",
      }),
    ).toBe("conflict");
    expect((await listExtractionReviews(reader, "SKIPPED", "", 0)).total).toBe(
      1,
    );
    const retry = (await listExtractionReviews(reader, "OPEN", "55000001", 0))
      .items[0];
    expect(
      await decideExtractionReview(reader, {
        id: retry.id,
        revision: retry.revision,
        action: "RETRY",
        feedback: "직무 이름 중복을 확인해 주세요",
      }),
    ).toBe("saved");
    expect(
      (
        await db.query(
          "SELECT review_result,review_feedback,reviewed_at FROM extraction_run WHERE id=$1",
          [retry.id],
        )
      ).rows[0],
    ).toMatchObject({
      review_result: "다시",
      review_feedback: "직무 이름 중복을 확인해 주세요",
    });
    expect(
      (await listExtractionReviews(reader, "RETRY_REQUESTED", "", 0)).total,
    ).toBe(1);
    const race = (await listExtractionReviews(reader, "OPEN", "55000002", 0))
      .items[0];
    contender = new Client({ connectionString: parsed.href });
    await contender.connect();
    await contender.query(`SET ROLE "${role}"`);
    const decisions = await Promise.all([
      decideExtractionReview(contender, {
        id: race.id,
        revision: race.revision,
        action: "PASS",
        feedback: "",
      }),
      decideExtractionReview(reader, {
        id: race.id,
        revision: race.revision,
        action: "RETRY",
        feedback: "본문 아래 확인",
      }),
    ]);
    expect(decisions.sort()).toEqual(["conflict", "saved"]);
    const stale = (await listExtractionReviews(reader, "OPEN", "55000003", 0))
      .items[0];
    await db.query("UPDATE extraction_run SET is_current=false WHERE id=$1", [
      stale.id,
    ]);
    expect(
      await decideExtractionReview(reader, {
        id: stale.id,
        revision: stale.revision,
        action: "PASS",
        feedback: "",
      }),
    ).toBe("conflict");
    await db.query(
      "UPDATE extraction_run SET review_reasons='[]' WHERE id=$1",
      [ids[4]],
    );
    expect(
      (await listExtractionReviews(reader, "ALL", "55000004", 0)).total,
    ).toBe(0);
    expect(
      await decideExtractionReview(reader, {
        id: ids[4],
        revision: token,
        action: "PASS",
        feedback: "",
      }),
    ).toBe("missing");
    await expect(
      reader.query("UPDATE extraction_run SET is_current=false WHERE id=$1", [
        ids[5],
      ]),
    ).rejects.toMatchObject({ code: "42501" });
    expect(
      (
        await db.query(
          "SELECT to_regclass('public.career_extraction_review') AS old",
        )
      ).rows[0].old,
    ).toBeNull();
    await db.query(
      "UPDATE extraction_run SET review_result='정상',reviewed_at=now() WHERE id=$1",
      [ids[5]],
    );
    expect((await listExtractionReviews(reader, "RESOLVED", "", 0)).total).toBe(
      1,
    );
    const cleanup = readFileSync(
      path.resolve("../deploy/web/retire-extraction-review.sql"),
      "utf8",
    );
    await db.query(
      "CREATE TABLE career_extraction_review(id int,status text,feedback text,revision int); CREATE TABLE career_extraction_review_event(id int); CREATE VIEW career_extraction_review_candidates AS SELECT id FROM career_extraction_review",
    );
    await db.query(
      "INSERT INTO career_extraction_review VALUES(1,'SKIPPED','',0)",
    );
    await expect(db.query(cleanup)).rejects.toMatchObject({ code: "P0001" });
    await db.query("ROLLBACK");
    expect(
      (
        await db.query(
          "SELECT count(*)::int AS n FROM career_extraction_review",
        )
      ).rows[0].n,
    ).toBe(1);
    await db.query("UPDATE career_extraction_review SET status='OPEN'");
    await db.query(cleanup);
    await db.query(cleanup);
    expect(
      (
        await db.query(
          "SELECT to_regclass('public.career_extraction_review') AS old,to_regclass('public.career_extraction_review_event') AS events,to_regclass('public.career_extraction_review_candidates') AS candidates",
        )
      ).rows[0],
    ).toEqual({ old: null, events: null, candidates: null });
    expect(
      (await listExtractionReviews(reader, "OPEN", "", 0)).total,
    ).toBeGreaterThan(0);
  } finally {
    await contender?.end();
    await reader?.end();
    await db?.end();
    await admin.query(`DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`);
    await admin.query(`DROP ROLE IF EXISTS "${role}"`);
    await admin.end();
  }
});
