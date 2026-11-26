import { test, expect } from "@playwright/test";
import { Client } from "pg";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { searchJobCatalog, type CatalogQuery } from "../lib/server/job-catalog";
import type { PublicJob } from "../types/public-job";
import {
  listPostingPublication,
  changePostingPublication,
} from "../lib/server/posting-publication";

test("catalog searches beyond 200, filters before paging, merges providers and reads only the current extraction", async () => {
  const url = process.env.TEST_DATABASE_URL;
  if (process.env.REQUIRE_REVIEW_DB === "1") expect(url).toBeTruthy();
  test.skip(!url, "Local isolated PostgreSQL required");
  const address = new URL(url!);
  expect(["127.0.0.1", "localhost", "[::1]"]).toContain(address.hostname);
  const name = "career_catalog_test_" + randomUUID().replaceAll("-", "");
  const admin = new Client({ connectionString: url });
  let db: Client | undefined;
  await admin.connect();
  try {
    await admin.query(`CREATE DATABASE "${name}"`);
    address.pathname = "/" + name;
    db = new Client({ connectionString: address.href });
    await db.connect();
    await db.query(
      readFileSync(path.resolve("../job-skill/db/schema.sql"), "utf8"),
    );
    await db.query(
      readFileSync(
        path.resolve("../db/migrations/11-posting-visibility.sql"),
        "utf8",
      ),
    );
    await db.query("INSERT INTO company(name) VALUES('검색검증회사')");
    await db.query(`INSERT INTO posting(company_id,site_posting_no,title,site_job_category,career_condition,kind,status,raw_hash,collected_at,deadline)
      SELECT 1,i::text,CASE i WHEN 1 THEN '200개 밖 API 개발자' WHEN 2 THEN '데이터 엔지니어' WHEN 3 THEN 'iOS 앱 개발자' ELSE 'Backend Engineer ' || i END,
        CASE i WHEN 3 THEN '모바일' ELSE '백엔드' END,CASE i%3 WHEN 0 THEN '신입' WHEN 1 THEN '경력무관' ELSE '경력' END,
        '글',CASE i WHEN 4 THEN '마감' ELSE '진행' END,repeat('a',64),'2026-01-01'::timestamptz+i*interval '1 second',
        CASE WHEN i%2=0 THEN DATE '2027-01-01'+i END FROM generate_series(1,230) i`);
    await db.query(`INSERT INTO extraction_run(posting_id,model,prompt_version,dict_version,input_hash,input_tokens,output_tokens,cost_usd,is_current)
      VALUES(1,'test','test','test',repeat('b',64),0,0,0,true),(1,'old','old','old',repeat('c',64),0,0,0,false)`);
    await db.query(
      "INSERT INTO recruit_unit(run_id,seq,name,is_it,job,career) VALUES(1,1,'개발',true,'백엔드','경력'),(2,1,'옛 개발',true,'백엔드','경력')",
    );
    await db.query(
      "INSERT INTO unit_item(unit_id,category,seq,text,quote) VALUES(1,'필수',1,'DuckDB 사용','원문'),(2,'필수',1,'OldSkill 사용','옛 원문')",
    );
    await db.query(
      "INSERT INTO capability(name) VALUES('DB'); INSERT INTO tech(name) VALUES('DuckDB'),('OldSkill')",
    );
    await db.query(
      "INSERT INTO requirement(item_id,capability_id,relation) VALUES(1,1,'능력만'),(2,1,'능력만')",
    );
    await db.query(
      "INSERT INTO requirement_tech(requirement_id,tech_id,written_name) VALUES(1,1,'duckdb'),(2,2,'oldskill')",
    );
    await db.query(`INSERT INTO extraction_run(posting_id,model,prompt_version,dict_version,input_hash,input_tokens,output_tokens,cost_usd,is_current)
      SELECT id,'test','test','test',repeat('d',64),0,0,0,true FROM posting WHERE id<>1;
      INSERT INTO recruit_unit(run_id,seq,name,is_it,job,career)
      SELECT id,1,'개발',true,CASE posting_id WHEN 2 THEN '데이터 엔지니어' WHEN 3 THEN '그 외' ELSE '백엔드' END,'언급없음' FROM extraction_run WHERE posting_id<>1;
      INSERT INTO unit_item(unit_id,category,seq,text,quote)
      SELECT u.id,'업무',1,'서비스 개발','원문' FROM recruit_unit u JOIN extraction_run e ON e.id=u.run_id WHERE e.posting_id<>1;`);
    const input: CatalogQuery = {
      query: "",
      role: "all",
      location: "",
      workplace: "all",
      experience: [],
      sort: "newest",
      offset: 0,
      limit: 12,
    };
    const extra: PublicJob = {
      id: "lever:one",
      title: "Backend remote",
      company: "외부회사",
      category: "backend",
      location: "서울",
      employment: "정규직",
      workplace: "원격 근무",
      postedAt: "2026-10-01T00:00:00Z",
      url: "https://jobs.lever.co/test/one",
      skills: ["Redis"],
      experience: ["entry"],
    };
    const all = await searchJobCatalog(db, input, [extra]);
    expect(all.total).toBe(229);
    expect(all.jobs).toHaveLength(12);
    expect(all.jobs[0].id).toBe("lever:one");
    expect(all.nextOffset).toBe(12);
    const seen = new Set<string>();
    for (let offset = 0; offset < all.total; offset += 24) {
      const page = await searchJobCatalog(db, { ...input, limit: 24, offset }, [
        extra,
      ]);
      for (const job of page.jobs) {
        expect(seen.has(job.id)).toBe(false);
        seen.add(job.id);
      }
    }
    expect(seen.size).toBe(229);
    expect(seen.has("be:1")).toBe(true);
    expect(seen.has("be:3")).toBe(false);
    expect(seen.has("be:4")).toBe(false);
    const old = await searchJobCatalog(db, { ...input, query: "200개 밖" }, []);
    expect(old.total).toBe(1);
    expect(old.jobs[0].id).toBe("be:1");
    expect(old.jobs[0].skills).toEqual(["DuckDB"]);
    expect(
      (await searchJobCatalog(db, { ...input, query: "duckdb" }, [])).jobs[0]
        .id,
    ).toBe("be:1");
    expect(
      (await searchJobCatalog(db, { ...input, query: "oldskill" }, [])).total,
    ).toBe(0);
    expect(
      (await searchJobCatalog(db, { ...input, query: "검색검증회사" }, []))
        .total,
    ).toBe(228);
    expect(
      (await searchJobCatalog(db, { ...input, role: "data" }, [])).jobs.map(
        (x) => x.id,
      ),
    ).toEqual(["be:2"]);
    expect(
      (
        await searchJobCatalog(db, { ...input, location: "서울" }, [extra])
      ).jobs.map((x) => x.id),
    ).toEqual(["lever:one"]);
    expect(
      (await searchJobCatalog(db, { ...input, workplace: "remote" }, [extra]))
        .total,
    ).toBe(1);
    const junior = await searchJobCatalog(
      db,
      { ...input, experience: ["entry"], limit: 24 },
      [extra],
    );
    expect(junior.jobs.every((job) => job.experience?.includes("entry"))).toBe(
      true,
    );
    const closing = await searchJobCatalog(
      db,
      { ...input, sort: "closing", limit: 24 },
      [extra],
    );
    expect(closing.jobs.every((job) => !!job.closesAt)).toBe(true);
    expect(closing.jobs.map((job) => job.closesAt)).toEqual(
      [...closing.jobs.map((job) => job.closesAt)].sort(),
    );
    expect(
      (
        await searchJobCatalog(db, { ...input, sort: "company" }, [extra])
      ).jobs.every((job) => job.company === "검색검증회사"),
    ).toBe(true);
    expect(
      (
        await searchJobCatalog(db, { ...input, sort: "company", offset: 228 }, [
          extra,
        ])
      ).jobs[0].id,
    ).toBe("lever:one");
    expect(
      (await searchJobCatalog(db, { ...input, query: "' OR 1=1 --" }, [extra]))
        .total,
    ).toBe(0);
    expect(
      (await searchJobCatalog(db, { ...input, offset: 300 }, [extra])).jobs,
    ).toEqual([]);
    const fixture = {
      ...extra,
      id: "dummy:one",
      title: "매칭 예시",
      dummy: true,
    };
    const examples = await searchJobCatalog(
      db,
      { ...input, query: "매칭 예시" },
      [fixture],
    );
    expect(examples.total).toBe(0);
    expect(examples.jobs).toEqual([]);
    await db.query(
      "UPDATE posting SET body_html='<p>근무지 : <span>서울 강남구</span></p><p>근무 방식 : 원격 근무</p>' WHERE id=1",
    );
    await db.query(
      "UPDATE posting SET deadline=(now() AT TIME ZONE 'Asia/Seoul')::date-1 WHERE id=2",
    );
    await db.query(
      "UPDATE posting SET deadline=(now() AT TIME ZONE 'Asia/Seoul')::date WHERE id=5",
    );
    const fresh = { query: db.query.bind(db) };
    const location = await searchJobCatalog(
      fresh,
      { ...input, location: "서울" },
      [],
    );
    expect(location.jobs.map((job) => job.id)).toEqual(["be:1"]);
    expect(location.jobs[0].location).toBe("서울 강남구");
    const remote = await searchJobCatalog(
      fresh,
      { ...input, workplace: "remote" },
      [],
    );
    expect(remote.jobs.map((job) => job.id)).toEqual(["be:1"]);
    expect(
      (
        await searchJobCatalog(
          fresh,
          { ...input, query: "200개 밖", experience: ["experienced"] },
          [],
        )
      ).total,
    ).toBe(1); // Current extraction explicitly requires experience.
    expect(
      (
        await searchJobCatalog(
          fresh,
          {
            ...input,
            query: "Backend Engineer 7",
            experience: ["experienced"],
            limit: 24,
          },
          [],
        )
      ).jobs.some((job) => job.id === "be:7"),
    ).toBe(false);
    expect(
      (await searchJobCatalog(fresh, { ...input, role: "data" }, [])).total,
    ).toBe(0);
    await db.query(
      "UPDATE posting SET skill_categories=ARRAY['L','B'] WHERE id=1; UPDATE posting SET skill_categories=ARRAY[]::text[] WHERE id=5",
    );
    expect(
      (await searchJobCatalog(db, { ...input, query: "200개 밖" }, [])).jobs[0]
        .skillCategories,
    ).toEqual(["L", "B"]);
    expect(
      (
        await searchJobCatalog(
          db,
          { ...input, query: "backend engineer 5", limit: 24 },
          [],
        )
      ).jobs.find((job) => job.id === "be:5")?.skillCategories,
    ).toEqual([]);
    expect(
      (
        await searchJobCatalog(
          db,
          { ...input, query: "backend engineer 7", limit: 24 },
          [],
        )
      ).jobs.find((job) => job.id === "be:7")?.skillCategories,
    ).toBeNull();
    // IT=true can still be excluded by the pipeline's finer job filter.
    await db.query("UPDATE recruit_unit SET job='그 외' WHERE run_id=1");
    expect(
      (await searchJobCatalog(db, { ...input, query: "200개 밖" }, [])).total,
    ).toBe(0);
    expect(
      (await listPostingPublication(db, "FILTERED", "200개 밖", 0)).total,
    ).toBe(1);
    await db.query("UPDATE recruit_unit SET job='백엔드' WHERE run_id=1");
    const remaining = await searchJobCatalog(
      fresh,
      { ...input, limit: 24, sort: "closing" },
      [],
    );
    expect(remaining.jobs.some((job) => job.id === "be:5")).toBe(true);
    expect(
      remaining.jobs.every(
        (job) => !job.closesAt || Date.parse(job.closesAt) >= Date.now(),
      ),
    ).toBe(true);

    const beforeReview = (
      await db.query(
        "SELECT review_result,review_feedback,reviewed_at FROM extraction_run WHERE id=1",
      )
    ).rows[0];
    const visible = await listPostingPublication(
      db,
      "PUBLISHED",
      "200개 밖",
      0,
    );
    expect(visible.items).toHaveLength(1);
    expect(
      await changePostingPublication(
        db,
        { id: "1", revision: 0, hidden: true },
        "admin-test",
      ),
    ).toBe(true);
    expect(
      (await searchJobCatalog(db, { ...input, query: "200개 밖" }, [])).total,
    ).toBe(0);
    expect(
      await changePostingPublication(
        db,
        { id: "1", revision: 0, hidden: true },
        "another-admin",
      ),
    ).toBe(false);
    const hidden = await listPostingPublication(db, "HIDDEN", "200개 밖", 0);
    expect(hidden.items[0].revision).toBe(1);
    expect(
      (
        await db.query(
          "SELECT review_result,review_feedback,reviewed_at FROM extraction_run WHERE id=1",
        )
      ).rows[0],
    ).toEqual(beforeReview);
    expect(
      await changePostingPublication(
        db,
        { id: "1", revision: 1, hidden: false },
        "admin-test",
      ),
    ).toBe(true);
    expect(
      (await searchJobCatalog(db, { ...input, query: "200개 밖" }, [])).total,
    ).toBe(1);
    await db.query("UPDATE recruit_unit SET is_it=false WHERE run_id=1");
    expect(
      (await searchJobCatalog(db, { ...input, query: "200개 밖" }, [])).total,
    ).toBe(0);
    expect(
      (await searchJobCatalog(db, { ...input, query: "duckdb" }, [])).total,
    ).toBe(0);
    expect(
      (await listPostingPublication(db, "FILTERED", "200개 밖", 0)).total,
    ).toBe(1);
    // An old IT extraction cannot bypass the current run's role filter.
    expect(
      await changePostingPublication(
        db,
        { id: "1", revision: 2, hidden: false },
        "admin-test",
      ),
    ).toBe(false);
    await db.query("UPDATE recruit_unit SET is_it=true WHERE run_id=1");
    await db.query("UPDATE unit_item SET text=' ' WHERE unit_id=1");
    expect(
      (await searchJobCatalog(db, { ...input, query: "200개 밖" }, [])).total,
    ).toBe(0);
    await db.query("UPDATE unit_item SET text='서비스 개발' WHERE unit_id=1");
    // Hide survives replacement of the current extraction run.
    expect(
      await changePostingPublication(
        db,
        { id: "1", revision: 2, hidden: true },
        "admin-test",
      ),
    ).toBe(true);
    await db.query(
      "UPDATE extraction_run SET is_current=false WHERE id=1; UPDATE extraction_run SET is_current=true WHERE id=2",
    );
    expect(
      (await searchJobCatalog(db, { ...input, query: "200개 밖" }, [])).total,
    ).toBe(0);
    await db.query(
      "UPDATE posting SET deadline=(now() AT TIME ZONE 'Asia/Seoul')::date-1 WHERE id=1",
    );
    expect(
      await changePostingPublication(
        db,
        { id: "1", revision: 3, hidden: false },
        "admin-test",
      ),
    ).toBe(false);
    expect(
      (await listPostingPublication(db, "HIDDEN", "200개 밖", 0)).items[0]
        .eligible,
    ).toBe(false);
  } finally {
    await db?.end();
    await admin.query(`DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`);
    await admin.end();
  }
});
