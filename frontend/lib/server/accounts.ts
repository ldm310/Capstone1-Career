import "server-only";
import { db } from "./store";
import { profilePool } from "./posting-levels";

export type Account = {
  id: string;
  email: string;
  name: string;
  password: string;
  age?: number | null;
  school?: string;
  major?: string;
};
const namespace = () => process.env.CAREER_PROFILE_NAMESPACE || "local-review";
const accountPool = () => {
  if (process.env.CAREER_ACCOUNT_STORE !== "rds") return null;
  const pool = profilePool();
  if (!pool) throw new Error("회원 데이터베이스 연결 설정이 필요합니다.");
  return pool;
};
const columns =
  "subject_id AS id,email,name,password_hash AS password,age,school,major";

// SQLite remains the local workspace/session store. RDS is authoritative for members.
function cache(account: Account) {
  db()
    .prepare(
      `INSERT INTO users(id,email,name,password) VALUES(?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET email=excluded.email,name=excluded.name,password=excluded.password`,
    )
    .run(account.id, account.email, account.name, account.password);
  return account;
}
export async function accountByEmail(
  email: string,
): Promise<Account | undefined> {
  const pool = accountPool();
  if (!pool)
    return db().prepare("SELECT * FROM users WHERE email=?").get(email) as
      Account | undefined;
  const { rows } = await pool.query<Account>(
    `SELECT ${columns} FROM public.career_account WHERE namespace=$1 AND email=$2`,
    [namespace(), email],
  );
  return rows[0] ? cache(rows[0]) : undefined;
}
export async function accountById(id: string): Promise<Account | undefined> {
  const pool = accountPool();
  if (!pool)
    return db().prepare("SELECT * FROM users WHERE id=?").get(id) as
      Account | undefined;
  const { rows } = await pool.query<Account>(
    `SELECT ${columns} FROM public.career_account WHERE namespace=$1 AND subject_id=$2`,
    [namespace(), id],
  );
  return rows[0] ? cache(rows[0]) : undefined;
}
export async function createAccount(account: Account) {
  const pool = accountPool();
  if (pool) {
    try {
      await pool.query(
        `INSERT INTO public.career_account(namespace,subject_id,email,name,password_hash,age,school,major) VALUES($1,$2,$3,$4,$5,$6,$7,$8)`,
        [
          namespace(),
          account.id,
          account.email,
          account.name,
          account.password,
          account.age ?? null,
          account.school || "",
          account.major || "",
        ],
      );
    } catch (error) {
      if (
        error &&
        typeof error === "object" &&
        "code" in error &&
        error.code === "23505"
      )
        throw new Error("이미 가입된 이메일입니다. 로그인해 주세요.");
      throw error;
    }
  }
  return cache(account);
}
export async function updateAccount(account: Account) {
  const pool = accountPool();
  if (pool) {
    const result = await pool.query(
      `UPDATE public.career_account SET email=$3,name=$4,password_hash=$5,age=$6,school=$7,major=$8,updated_at=now() WHERE namespace=$1 AND subject_id=$2`,
      [
        namespace(),
        account.id,
        account.email,
        account.name,
        account.password,
        account.age ?? null,
        account.school || "",
        account.major || "",
      ],
    );
    if (!result.rowCount) throw new Error("회원 정보를 찾을 수 없습니다.");
  }
  return cache(account);
}
export async function kakaoAccount(
  subject: string,
): Promise<Account | undefined> {
  const pool = accountPool();
  if (pool) {
    const { rows } = await pool.query<Account>(
      `SELECT a.subject_id AS id,a.email,a.name,a.password_hash AS password,a.age,a.school,a.major
      FROM public.career_account_oauth o JOIN public.career_account a USING(namespace,subject_id)
      WHERE o.namespace=$1 AND o.provider='kakao' AND o.provider_subject=$2`,
      [namespace(), subject],
    );
    return rows[0] ? cache(rows[0]) : undefined;
  }
  return db()
    .prepare(
      "SELECT u.* FROM oauth_accounts o JOIN users u ON u.id=o.user_id WHERE o.provider='kakao' AND o.subject=?",
    )
    .get(subject) as Account | undefined;
}
export async function createKakaoAccount(account: Account, subject: string) {
  const pool = accountPool();
  if (pool) {
    const connection = await pool.connect();
    try {
      await connection.query("BEGIN");
      await connection.query(
        `INSERT INTO public.career_account(namespace,subject_id,email,name,password_hash) VALUES($1,$2,$3,$4,$5)`,
        [
          namespace(),
          account.id,
          account.email,
          account.name,
          account.password,
        ],
      );
      await connection.query(
        `INSERT INTO public.career_account_oauth(namespace,provider,provider_subject,subject_id) VALUES($1,'kakao',$2,$3)`,
        [namespace(), subject, account.id],
      );
      await connection.query("COMMIT");
    } catch (error) {
      await connection.query("ROLLBACK");
      if (
        error &&
        typeof error === "object" &&
        "code" in error &&
        error.code === "23505"
      ) {
        const { rows } = await connection.query<Account>(
          `SELECT a.subject_id AS id,a.email,a.name,a.password_hash AS password,a.age,a.school,a.major
           FROM public.career_account_oauth o JOIN public.career_account a USING(namespace,subject_id)
           WHERE o.namespace=$1 AND o.provider='kakao' AND o.provider_subject=$2`,
          [namespace(), subject],
        );
        if (rows[0]) return cache(rows[0]);
        throw new Error("ACCOUNT_LINK_REQUIRED");
      }
      throw error;
    } finally {
      connection.release();
    }
    return cache(account);
  }
  const local = db();
  local.exec("BEGIN IMMEDIATE");
  try {
    cache(account);
    local
      .prepare("INSERT INTO oauth_accounts VALUES('kakao',?,?)")
      .run(subject, account.id);
    local.exec("COMMIT");
    return account;
  } catch (error) {
    local.exec("ROLLBACK");
    throw error;
  }
}
