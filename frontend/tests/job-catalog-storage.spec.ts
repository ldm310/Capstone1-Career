import { test, expect } from "@playwright/test";
import { Client } from "pg";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { searchJobCatalog, type CatalogQuery } from "../lib/server/job-catalog";
import type { PublicJob } from "../types/public-job";

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
    await db.query("INSERT INTO company(name) VALUES('검색검증회사')");
    await db.query(`INSERT INTO posting(company_id,site_posting_no,title,site_job_category,career_condition,kind,status,raw_hash,collected_at,deadline)
      SELECT 1,i::text,CASE i WHEN 1 THEN '200개 밖 API 개발자' WHEN 2 THEN '데이터 엔지니어' WHEN 3 THEN 'iOS 앱 개발자' ELSE 'Backend Engineer ' || i END,
        CASE i WHEN 3 THEN '모바일' ELSE '백엔드' END,CASE i%3 WHEN 0 THEN '신입' WHEN 1 THEN '경력무관' ELSE '경력' END,
        '글',CASE i WHEN 4 THEN '마감' ELSE '진행' END,repeat('a',64),'2026-01-01'::timestamptz+i*interval '1 second',
        CASE WHEN i%2=0 THEN DATE '2027-01-01'+i END FROM generate_series(1,230) i`);
    await db.query(`INSERT INTO extraction_run(posting_id,model,prompt_version,dict_version,input_hash,input_tokens,output_tokens,cost_usd,is_current)
      VALUES(1,'test','test','test',repeat('b',64),0,0,0,true),(1,'old','old','old',repeat('c',64),0,0,0,false)`);
    await db.query(
      "INSERT INTO recruit_unit(run_id,seq,name,is_it,career) VALUES(1,1,'개발',true,'경력'),(2,1,'옛 개발',true,'경력')",
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
    expect((await searchJobCatalog(fresh,{...input,query:"200개 밖",experience:["experienced"]},[])).total).toBe(1); // Current extraction explicitly requires experience.
    expect((await searchJobCatalog(fresh,{...input,query:"Backend Engineer 7",experience:["experienced"],limit:24},[])).jobs.some(job=>job.id==="be:7")).toBe(false);
    expect(
      (await searchJobCatalog(fresh, { ...input, role: "data" }, [])).total,
    ).toBe(0);
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
  } finally {
    await db?.end();
    await admin.query(`DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`);
    await admin.end();
  }
});
