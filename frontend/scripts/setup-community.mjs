// Administrator CLI. No credentials or one-time activation tokens are printed.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes, randomUUID, scryptSync, createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import pg from "pg";
const front = path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."),
  root = path.dirname(front);
const args = process.argv.slice(2);
const option = (name) =>
  args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const env = Object.fromEntries(
  readFileSync(option("--env-file") || path.join(front, ".env.local"), "utf8")
    .split(/\r?\n/)
    .filter((line) => line.includes("=") && !line.startsWith("#"))
    .map((line) => {
      const i = line.indexOf("=");
      const raw = line.slice(i + 1).trim();
      const value =
        raw.startsWith('"') && raw.endsWith('"')
          ? JSON.parse(raw)
          : raw.startsWith("'") && raw.endsWith("'")
            ? raw.slice(1, -1)
            : raw;
      return [line.slice(0, i).trim(), value];
    }),
);
const client = new pg.Client({
  connectionString: env.CAREER_PROFILE_DATABASE_URL,
  ssl: {
    ca: readFileSync(env.CAREER_PROFILE_CA_FILE, "utf8"),
    rejectUnauthorized: true,
  },
  connectionTimeoutMillis: 10000,
});
const namespace = env.CAREER_PROFILE_NAMESPACE || "local-review";
const email = args.includes("--admin")
  ? args[args.indexOf("--admin") + 1]?.toLowerCase()
  : null;
if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
  throw new Error("Invalid administrator email");
if (email === "demo@career.dev")
  throw new Error("Public demo credentials cannot manage notices");
const hashPassword = (value) => {
  const salt = randomBytes(16).toString("hex");
  return `${salt}:${scryptSync(value, salt, 64).toString("hex")}`;
};
try {
  await client.connect();
  await client.query(
    readFileSync(
      path.join(root, "db/migrations/06-user-posting-levels.sql"),
      "utf8",
    ),
  );
  await client.query(
    readFileSync(path.join(root, "db/migrations/07-notices-admin.sql"), "utf8"),
  );
  await client.query(
    `INSERT INTO public.career_lv_member(namespace,subject_id) VALUES($1,'career-system') ON CONFLICT DO NOTHING`,
    [namespace],
  );
  const notices = [
    [
      "career-guide",
      "Career 이용 안내",
      "채용공고는 로그인 없이 확인할 수 있습니다.\n\n개인 역량 분석은 로그인 후 이용할 수 있습니다. 분석 메뉴에서 GitHub 링크나 PDF 이력서를 등록한 뒤, 각 채용공고의 역량 분석 탭에서 비교 결과를 확인하세요.",
      true,
    ],
    [
      "career-resume",
      "Career 이력서 양식 안내",
      "분석 메뉴에서 Career 이력서 Word 양식과 PDF 양식을 받을 수 있습니다.\n\nWord 양식에 내용을 작성한 뒤 PDF로 저장해 등록하세요. 이력서 파일은 PDF 형식만 지원합니다. GitHub 링크와 이력서는 둘 중 하나 이상 등록하면 됩니다.",
      false,
    ],
  ];
  for (const [id, title, content, pinned] of notices)
    await client.query(
      `INSERT INTO public.career_notice(namespace,id,title,content,pinned,author_id,author_name) VALUES($1,$2,$3,$4,$5,'career-system','Career') ON CONFLICT DO NOTHING`,
      [namespace, id, title, content, pinned],
    );
  await client.query(
    readFileSync(path.join(root, "db/migrations/08-user-accounts.sql"), "utf8"),
  );
  await client.query(
    readFileSync(
      path.join(root, "job-skill/db/migrations/008_extraction_review.sql"),
      "utf8",
    ),
  );
  const hasPostings = await client.query(
    "SELECT to_regclass('public.posting') IS NOT NULL AND to_regclass('public.extraction_run') IS NOT NULL AS available",
  );
  if (hasPostings.rows[0].available) {
    await client.query(
      readFileSync(
        path.join(
          root,
          "job-skill/db/migrations/009_review_required_candidates.sql",
        ),
        "utf8",
      ),
    );
    await client.query(
      readFileSync(
        path.join(root, "job-skill/db/sync_extraction_review.sql"),
        "utf8",
      ),
      [namespace],
    );
  }
  const report = { migrationApplied: true, starterNotices: 2 };
  const sourceNamespace = option("--seed-demo-from");
  if (sourceNamespace) {
    if (sourceNamespace === namespace)
      throw new Error("Demo source and destination must differ");
    await client.query("BEGIN");
    try {
      const source = await client.query(
        `SELECT 1 FROM public.career_lv_member WHERE namespace=$1 AND subject_id='demo-user' AND is_demo`,
        [sourceNamespace],
      );
      if (!source.rowCount) throw new Error("Demo source is not provisioned");
      await client.query(
        `INSERT INTO public.career_lv_member(namespace,subject_id,is_demo) VALUES($1,'demo-user',true) ON CONFLICT DO NOTHING`,
        [namespace],
      );
      const target = await client.query(
        `SELECT is_demo FROM public.career_lv_member WHERE namespace=$1 AND subject_id='demo-user'`,
        [namespace],
      );
      if (!target.rows[0]?.is_demo)
        throw new Error("Cannot replace a real member with a demo");
      await client.query(
        `INSERT INTO public.career_lv_analysis_source(namespace,subject_id,source_id,kind,title,locator,is_simulated)
        SELECT $1,subject_id,source_id,kind,title,locator,true FROM public.career_lv_analysis_source
        WHERE namespace=$2 AND subject_id='demo-user' AND is_simulated ON CONFLICT DO NOTHING`,
        [namespace, sourceNamespace],
      );
      await client.query(
        `INSERT INTO public.career_lv_posting_keyword_level(namespace,subject_id,job_id,keyword_id,taxonomy_version,keyword_text,category_codes,score,reference_score,reference_kind,evidence_source_ids,evaluation_kind,method_version)
        SELECT $1,subject_id,job_id,keyword_id,taxonomy_version,keyword_text,category_codes,score,reference_score,reference_kind,evidence_source_ids,evaluation_kind,method_version
        FROM public.career_lv_posting_keyword_level WHERE namespace=$2 AND subject_id='demo-user' AND evaluation_kind='DEMO' ON CONFLICT DO NOTHING`,
        [namespace, sourceNamespace],
      );
      await client.query("COMMIT");
      const counts = await client.query(
        `SELECT count(*)::int AS levels,count(DISTINCT job_id)::int AS jobs FROM public.career_lv_posting_keyword_level WHERE namespace=$1 AND subject_id='demo-user' AND evaluation_kind='DEMO'`,
        [namespace],
      );
      if (!counts.rows[0].levels)
        throw new Error("Demo levels are not provisioned");
      report.demo = counts.rows[0];
      report.namespace = namespace;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => {});
      throw error;
    }
  }
  if (email) {
    const d = new DatabaseSync(
      path.resolve(
        front,
        env.CAREER_DATA_DIR || ".career-data",
        "career.sqlite",
      ),
    );
    d.exec(
      `PRAGMA foreign_keys=ON; CREATE TABLE IF NOT EXISTS admin_invitations(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires INTEGER NOT NULL,used_at INTEGER);`,
    );
    let account = d.prepare("SELECT id FROM users WHERE email=?").get(email),
      created = false;
    if (!account) {
      account = { id: randomUUID() };
      d.prepare("INSERT INTO users VALUES(?,?,?,?)").run(
        account.id,
        email,
        "관리자",
        hashPassword(randomBytes(48).toString("hex")),
      );
      created = true;
    }
    if (env.CAREER_ACCOUNT_STORE === "rds") {
      const identity = d
        .prepare("SELECT id,email,name,password FROM users WHERE id=?")
        .get(account.id);
      await client.query(
        `INSERT INTO public.career_account(namespace,subject_id,email,name,password_hash) VALUES($1,$2,$3,$4,$5) ON CONFLICT(namespace,subject_id) DO NOTHING`,
        [
          namespace,
          identity.id,
          identity.email,
          identity.name,
          identity.password,
        ],
      );
    }
    await client.query(
      `INSERT INTO public.career_lv_member(namespace,subject_id,app_role) VALUES($1,$2,'ADMIN') ON CONFLICT(namespace,subject_id) DO UPDATE SET app_role='ADMIN'`,
      [namespace, account.id],
    );
    if (created) {
      const token = randomBytes(32).toString("hex");
      d.prepare("INSERT INTO admin_invitations VALUES(?,?,?,NULL)").run(
        createHash("sha256").update(token).digest("hex"),
        account.id,
        Date.now() + 86400000,
      );
      const activation = `http://127.0.0.1:3000/admin/setup#token=${token}`;
      const file = path.join(front, "work/admin-first-login.html");
      mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(
        file,
        `<!doctype html><html lang="ko"><meta charset="utf-8"><title>Career 관리자 계정 설정</title><style>body{font-family:sans-serif;max-width:650px;margin:80px auto;padding:24px;line-height:1.8;color:#243f53}a{display:inline-block;padding:12px 20px;background:#315e7e;color:white;border-radius:8px}</style><h1>관리자 계정 준비 완료</h1><p>${email}</p><p>비밀번호를 직접 설정한 뒤 공지사항을 작성할 수 있습니다.</p><a href="${activation}">관리자 비밀번호 설정</a><p>이 링크는 24시간 안에 한 번 사용할 수 있습니다. 공유하지 마세요.</p></html>`,
        { mode: 0o600 },
      );
      report.activationFile = "frontend/work/admin-first-login.html";
    }
    report.adminEmail = email;
    report.newAccount = created;
    d.close();
  }
  // Keep IDs and password hashes so existing LV ownership and roles stay valid.
  const sqliteFile = path.resolve(
    front,
    env.CAREER_DATA_DIR || ".career-data",
    "career.sqlite",
  );
  report.accounts = { imported: 0, oauthImported: 0 };
  if (args.includes("--migrate-accounts") && existsSync(sqliteFile)) {
    const local = new DatabaseSync(sqliteFile, { readOnly: true });
    try {
      const tables = new Set(
        local
          .prepare("SELECT name FROM sqlite_master WHERE type='table'")
          .all()
          .map((row) => row.name),
      );
      await client.query("BEGIN");
      if (tables.has("users"))
        for (const account of local
          .prepare("SELECT id,email,name,password FROM users")
          .all()) {
          if (
            tables.has("guests") &&
            local
              .prepare("SELECT 1 FROM guests WHERE user_id=?")
              .get(account.id)
          )
            continue;
          let details = {};
          if (tables.has("profiles")) {
            const saved = local
              .prepare("SELECT data FROM profiles WHERE user_id=?")
              .get(account.id);
            try {
              details = saved ? JSON.parse(saved.data) : {};
            } catch {
              /* Optional fields stay blank. */
            }
          }
          const result = await client.query(
            `INSERT INTO public.career_account(namespace,subject_id,email,name,password_hash,age,school,major)
          VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(namespace,subject_id) DO NOTHING`,
            [
              namespace,
              account.id,
              account.email.toLowerCase(),
              account.name,
              account.password,
              Number.isInteger(details.age) &&
              details.age >= 0 &&
              details.age <= 120
                ? details.age
                : null,
              String(details.school || "").slice(0, 60),
              String(details.major || "").slice(0, 60),
            ],
          );
          report.accounts.imported += result.rowCount;
        }
      if (tables.has("oauth_accounts"))
        for (const identity of local
          .prepare("SELECT provider,subject,user_id FROM oauth_accounts")
          .all()) {
          if (identity.provider !== "kakao") continue;
          const result = await client.query(
            `INSERT INTO public.career_account_oauth(namespace,provider,provider_subject,subject_id)
          VALUES($1,'kakao',$2,$3) ON CONFLICT DO NOTHING`,
            [namespace, identity.subject, identity.user_id],
          );
          report.accounts.oauthImported += result.rowCount;
        }
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      local.close();
    }
  }
  const reportFile =
    option("--report-file") ||
    path.join(root, "work/community-setup-20261123.json");
  mkdirSync(path.dirname(reportFile), { recursive: true });
  writeFileSync(reportFile, JSON.stringify(report, null, 2), { mode: 0o600 });
  console.log(JSON.stringify(report));
} catch (error) {
  console.error(
    JSON.stringify({
      error: "Community setup failed",
      code: error.code || error.name,
    }),
  );
  process.exitCode = 1;
} finally {
  await client.end();
}
