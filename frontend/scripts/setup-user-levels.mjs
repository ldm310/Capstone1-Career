// Explicit administrator CLI only. Never runs during requests or deployment.
// Usage: node scripts/setup-user-levels.mjs --env ../work/career-team-write.env --apply --seed-demo --configure-local
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import pg from "pg";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const args = process.argv.slice(2);
const envFile = args[args.indexOf("--env") + 1];
if (!args.includes("--env") || !envFile)
  throw new Error("Provide --env credential file");
const settings = Object.fromEntries(
  readFileSync(path.resolve(envFile), "utf8")
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter(
      (line) =>
        line.trim() && !line.trim().startsWith("#") && line.includes("="),
    )
    .map((line) => {
      const index = line.indexOf("=");
      return [
        line.slice(0, index).trim(),
        line
          .slice(index + 1)
          .trim()
          .replace(/^['"]|['"]$/g, ""),
      ];
    }),
);
if (!settings.DATABASE_URL && !settings.PGHOST)
  throw new Error("Database settings missing");
const url = settings.DATABASE_URL
  ? new URL(settings.DATABASE_URL)
  : new URL(
      `postgresql://${settings.PGHOST}:${settings.PGPORT || "5432"}/${settings.PGDATABASE}`,
    );
if (!settings.DATABASE_URL) {
  url.username = settings.PGUSER;
  url.password = settings.PGPASSWORD;
}
for (const key of [
  "sslmode",
  "sslcert",
  "sslkey",
  "sslrootcert",
  "uselibpqcompat",
])
  url.searchParams.delete(key);
const connectionString = url.toString();
const caFile = path.join(root, "work/rds-ap-northeast-2-ca.pem");
const client = new pg.Client({
  connectionString,
  ssl: { ca: readFileSync(caFile, "utf8"), rejectUnauthorized: true },
  connectionTimeoutMillis: 10000,
  statement_timeout: 20000,
});
const namespace = "local-review";
const subject = "demo-user";
const catalog = JSON.parse(
  readFileSync(
    path.join(
      root,
      "backend/src/main/resources/skill-categories/reviewed-20261119.json",
    ),
    "utf8",
  ),
);
const examples = JSON.parse(
  readFileSync(
    path.join(root, "frontend/mock/reviewed-keyword-examples.json"),
    "utf8",
  ),
);
const codes = new Set(catalog.catalog.categories.map((c) => c.code));
const fingerprint = (text) =>
  createHash("sha256")
    .update(text.normalize("NFC").replace(/\s+/gu, " ").trim())
    .digest("hex");
const score = (id, keyword, salt) =>
  25 +
  (createHash("sha256").update(`${id}:${keyword}:${salt}`).digest()[0] % 71);
try {
  await client.connect();
  if (args.includes("--verify")) {
    const verify = await client.query(
      `SELECT job_id AS "jobId", count(*)::int AS keywords
      FROM public.career_lv_posting_keyword_level
      WHERE namespace=$1 AND subject_id=$2 AND job_id LIKE 'be:%'
      GROUP BY job_id HAVING count(*) >= 3 ORDER BY max(evaluated_at) DESC,job_id DESC LIMIT 3`,
      [namespace, subject],
    );
    console.log(JSON.stringify({ savedRdsJobs: verify.rows }));
  }
  if (args.includes("--check")) {
    const check =
      await client.query(`SELECT has_database_privilege(current_database(),'CREATE') AS "canCreateSchema",
      COALESCE((SELECT has_schema_privilege(oid,'CREATE') FROM pg_namespace WHERE nspname='profile'),false) AS "canCreateInProfile",
      COALESCE((SELECT has_schema_privilege(oid,'CREATE') FROM pg_namespace WHERE nspname='public'),false) AS "canCreateInPublic"`);
    console.log(JSON.stringify(check.rows[0]));
  }
  if (args.includes("--apply")) {
    await client.query(
      readFileSync(
        path.join(root, "db/migrations/06-user-posting-levels.sql"),
        "utf8",
      ),
    );
  }
  const report = { namespace, migrationApplied: args.includes("--apply") };
  if (args.includes("--seed-demo")) {
    const { rows: items } =
      await client.query(`SELECT e.posting_id, i.id, i.text
      FROM public.unit_item i JOIN public.recruit_unit u ON u.id=i.unit_id
      JOIN public.extraction_run e ON e.id=u.run_id
      WHERE e.is_current AND i.category IN ('필수','우대') ORDER BY e.posting_id,i.id`);
    const levels = items.flatMap((item) => {
      const entry = catalog.entries[fingerprint(item.text)];
      if (!entry || entry.excluded || entry.needsReview) return [];
      const categories = entry.categoryCodes.filter((code) => codes.has(code));
      return categories.length
        ? [
            {
              jobId: `be:${item.posting_id}`,
              id: String(item.id),
              text: item.text,
              categoryCodes: categories,
            },
          ]
        : [];
    });
    const dummyText = readFileSync(
      path.join(root, "frontend/lib/dummy-jobs.ts"),
      "utf8",
    );
    const dummyIds = [...dummyText.matchAll(/id: "(dummy:[^"]+)"/g)].map(
      (m) => m[1],
    );
    for (const jobId of [
      ...dummyIds,
      "study-demo-backend",
      "study-demo-data",
    ]) {
      for (const keyword of examples.examples)
        levels.push({ ...keyword, jobId });
    }
    await client.query("BEGIN");
    await client.query(
      `INSERT INTO public.career_lv_member(namespace,subject_id,is_demo) VALUES($1,$2,true)
      ON CONFLICT(namespace,subject_id) DO NOTHING`,
      [namespace, subject],
    );
    const member = await client.query(
      "SELECT is_demo FROM public.career_lv_member WHERE namespace=$1 AND subject_id=$2",
      [namespace, subject],
    );
    if (!member.rows[0]?.is_demo)
      throw new Error("Refusing to seed a real member");
    for (const source of [
      [
        "demo-github",
        "GITHUB",
        "주문 서비스 GitHub (등록 가정)",
        "https://github.com/career-demo/order-service",
      ],
      [
        "demo-pdf",
        "PDF",
        "Career 이력서.pdf (등록 가정)",
        "demo://career-resume.pdf",
      ],
    ])
      await client.query(
        `INSERT INTO public.career_lv_analysis_source(namespace,subject_id,source_id,kind,title,locator,is_simulated)
      VALUES($1,$2,$3,$4,$5,$6,true) ON CONFLICT DO NOTHING`,
        [namespace, subject, ...source],
      );
    for (const keyword of levels) {
      await client.query(
        `INSERT INTO public.career_lv_posting_keyword_level
        (namespace,subject_id,job_id,keyword_id,taxonomy_version,keyword_text,category_codes,
         score,reference_score,reference_kind,evidence_source_ids,evaluation_kind,method_version)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'SYNTHETIC_APPLICANTS',ARRAY['demo-github','demo-pdf'],'DEMO','demo-fixture-v1')
        ON CONFLICT(namespace,subject_id,job_id,keyword_id,taxonomy_version) DO UPDATE
        SET score=excluded.score, reference_score=excluded.reference_score
        WHERE career_lv_posting_keyword_level.evaluation_kind='DEMO'`,
        [
          namespace,
          subject,
          keyword.jobId,
          keyword.id,
          catalog.catalog.version,
          keyword.text,
          keyword.categoryCodes,
          score(keyword.jobId, keyword.id, "mine"),
          score(keyword.jobId, keyword.id, "reference"),
        ],
      );
    }
    await client.query("COMMIT");
    const { rows } = await client.query(
      `SELECT count(*)::int AS keywords,count(DISTINCT job_id)::int AS jobs,
      min(score)::int AS minimum,max(score)::int AS maximum FROM public.career_lv_posting_keyword_level
      WHERE namespace=$1 AND subject_id=$2 AND evaluation_kind='DEMO'`,
      [namespace, subject],
    );
    report.demo = rows[0];
    report.realUsersTouched = 0;
  }
  if (args.includes("--configure-local")) {
    const local = path.join(root, "frontend/.env.local");
    const original = readFileSync(local, "utf8");
    const kept = original
      .split(/\r?\n/)
      .filter(
        (line) =>
          !/^CAREER_PROFILE_(DATABASE_URL|NAMESPACE|CA_FILE)=/.test(line),
      );
    writeFileSync(
      local,
      kept.join("\n").trimEnd() +
        "\nCAREER_PROFILE_DATABASE_URL=" +
        connectionString +
        "\nCAREER_PROFILE_NAMESPACE=" +
        namespace +
        "\nCAREER_PROFILE_CA_FILE=" +
        caFile.replaceAll("\\", "/") +
        "\n",
    );
    report.localConfigured = true;
  }
  if (args.includes("--apply") || args.includes("--seed-demo"))
    writeFileSync(
      path.join(root, "work/user-level-rds-20261122.json"),
      JSON.stringify(report, null, 2),
    );
  console.log(JSON.stringify(report));
} catch (error) {
  await client.query("ROLLBACK").catch(() => {});
  // Do not print connection strings, database error details or env values.
  console.error(
    JSON.stringify({
      error: "RDS setup failed",
      code: error.code || error.name,
    }),
  );
  process.exitCode = 1;
} finally {
  await client.end();
}
