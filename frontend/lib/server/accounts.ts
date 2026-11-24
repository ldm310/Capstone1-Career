import "server-only";
import { db, revokeSessions } from "./store";
import { profilePool } from "./posting-levels";

export type Account = {
  id: string;
  email: string;
  name: string;
  password: string;
  age?: number | null;
  school?: string;
  major?: string;
  passwordSet?: boolean;
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
      `UPDATE public.career_account SET email=$3,name=$4,age=$5,school=$6,major=$7,updated_at=now() WHERE namespace=$1 AND subject_id=$2`,
      [
        namespace(),
        account.id,
        account.email,
        account.name,
        account.age ?? null,
        account.school || "",
        account.major || "",
      ],
    );
    if (!result.rowCount) throw new Error("회원 정보를 찾을 수 없습니다.");
  }
  const current = await accountById(account.id);
  if (!current) throw new Error("회원 정보를 찾을 수 없습니다.");
  if (!pool) {
    db()
      .prepare("UPDATE users SET email=?,name=? WHERE id=?")
      .run(account.email, account.name, account.id);
    return { ...account, password: current.password };
  }
  return cache(current);
}
export async function changeAccountPassword(
  account: Account,
  password: string,
) {
  const pool = accountPool();
  if (pool) {
    const connection = await pool.connect();
    try {
      await connection.query("BEGIN");
      const result = await connection.query(
        "UPDATE public.career_account SET password_hash=$4,updated_at=now() WHERE namespace=$1 AND subject_id=$2 AND password_hash=$3 AND email=$5 RETURNING subject_id",
        [namespace(), account.id, account.password, password, account.email],
      );
      if (!result.rowCount)
        throw new Error("회원 정보가 변경됐습니다. 다시 시도해 주세요.");
      await connection.query(
        "UPDATE public.career_account_oauth SET password_set_at=now() WHERE namespace=$1 AND subject_id=$2",
        [namespace(), account.id],
      );
      await connection.query("COMMIT");
    } catch (error) {
      await connection.query("ROLLBACK");
      throw error;
    } finally {
      connection.release();
    }
  } else {
    const result = db()
      .prepare(
        "UPDATE users SET password=? WHERE id=? AND password=? AND email=?",
      )
      .run(password, account.id, account.password, account.email);
    if (!result.changes)
      throw new Error("회원 정보가 변경됐습니다. 다시 시도해 주세요.");
    db()
      .prepare("UPDATE oauth_accounts SET password_set_at=? WHERE user_id=?")
      .run(Date.now(), account.id);
  }
  const updated = cache({ ...account, password, passwordSet: true });
  revokeSessions(account.id);
  return updated;
}
export async function kakaoAccount(
  subject: string,
): Promise<Account | undefined> {
  return oauthAccount("kakao", subject);
}
export async function oauthAccount(
  provider: "kakao" | "naver",
  subject: string,
): Promise<Account | undefined> {
  const pool = accountPool();
  if (pool) {
    const { rows } = await pool.query<Account>(
      `SELECT a.subject_id AS id,a.email,a.name,a.password_hash AS password,a.age,a.school,a.major,(o.password_set_at IS NOT NULL) AS "passwordSet"
      FROM public.career_account_oauth o JOIN public.career_account a USING(namespace,subject_id)
      WHERE o.namespace=$1 AND o.provider=$2 AND o.provider_subject=$3`,
      [namespace(), provider, subject],
    );
    return rows[0] ? cache(rows[0]) : undefined;
  }
  return db()
    .prepare(
      "SELECT u.*,(o.password_set_at IS NOT NULL) AS passwordSet FROM oauth_accounts o JOIN users u ON u.id=o.user_id WHERE o.provider=? AND o.subject=?",
    )
    .get(provider, subject) as Account | undefined;
}
export async function createKakaoAccount(account: Account, subject: string) {
  return createOAuthAccount(account, subject, "kakao", true);
}
export async function createOAuthAccount(
  account: Account,
  subject: string,
  provider: "kakao" | "naver",
  passwordSet = false,
) {
  const pool = accountPool();
  if (pool) {
    const connection = await pool.connect();
    try {
      await connection.query("BEGIN");
      await connection.query(
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
      await connection.query(
        `INSERT INTO public.career_account_oauth(namespace,provider,provider_subject,subject_id,password_set_at) VALUES($1,$2,$3,$4,CASE WHEN $5 THEN now() ELSE NULL END)`,
        [namespace(), provider, subject, account.id, passwordSet],
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
        throw new Error(
          "이미 가입된 계정입니다. 로그인 화면에서 다시 진행해 주세요.",
        );
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
      .prepare(
        "INSERT INTO oauth_accounts(provider,subject,user_id,password_set_at) VALUES(?,?,?,?)",
      )
      .run(provider, subject, account.id, passwordSet ? Date.now() : null);
    local.exec("COMMIT");
    return account;
  } catch (error) {
    local.exec("ROLLBACK");
    throw error;
  }
}

export async function accountPasswordConfigured(id: string) {
  const pool = accountPool();
  if (pool) {
    const { rows } = await pool.query(
      "SELECT 1 FROM public.career_account_oauth WHERE namespace=$1 AND subject_id=$2 AND password_set_at IS NULL LIMIT 1",
      [namespace(), id],
    );
    return rows.length === 0;
  }
  return !db()
    .prepare(
      "SELECT 1 FROM oauth_accounts WHERE user_id=? AND password_set_at IS NULL LIMIT 1",
    )
    .get(id);
}
