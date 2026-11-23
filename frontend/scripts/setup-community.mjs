// Administrator CLI. No credentials or one-time activation tokens are printed.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes, randomUUID, scryptSync, createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import pg from "pg";
const front = path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."),
  root = path.dirname(front);
const env = Object.fromEntries(
  readFileSync(path.join(front, ".env.local"), "utf8")
    .split(/\r?\n/)
    .filter((line) => line.includes("=") && !line.startsWith("#"))
    .map((line) => {
      const i = line.indexOf("=");
      return [line.slice(0, i), line.slice(i + 1)];
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
const args = process.argv.slice(2),
  email = args.includes("--admin")
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
  const report = { migrationApplied: true, starterNotices: 2 };
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
  writeFileSync(
    path.join(root, "work/community-setup-20261123.json"),
    JSON.stringify(report, null, 2),
  );
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
