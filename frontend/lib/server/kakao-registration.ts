import "server-only";
import { randomBytes, randomUUID, createHash } from "node:crypto";
import { cookies } from "next/headers";
import { db, credentialStamp, passwordHash } from "./store";
import {
  accountByEmail,
  kakaoAccount,
  createKakaoAccount,
  changeAccountPassword,
} from "./accounts";

const cookieName = "career_kakao_registration";
const tokenHash = (value: string) =>
  createHash("sha256").update(value).digest("hex");
type Pending = {
  token_hash: string;
  subject: string;
  email: string;
  name: string;
  account_id: string | null;
  credential_stamp: string | null;
  expires: number;
  used_at: number | null;
};
function table() {
  const connection = db();
  connection.exec(`CREATE TABLE IF NOT EXISTS kakao_registration(
    token_hash TEXT PRIMARY KEY,subject TEXT NOT NULL,email TEXT NOT NULL,name TEXT NOT NULL,
    account_id TEXT,credential_stamp TEXT,expires INTEGER NOT NULL,used_at INTEGER)`);
  return connection;
}
export async function beginKakaoRegistration(identity: {
  subject: string;
  email: string;
  name: string;
  accountId?: string;
  password?: string;
}) {
  const token = randomBytes(32).toString("hex");
  const connection = table();
  connection
    .prepare(
      "DELETE FROM kakao_registration WHERE expires<? OR used_at IS NOT NULL",
    )
    .run(Date.now());
  connection
    .prepare("INSERT INTO kakao_registration VALUES(?,?,?,?,?,?,?,NULL)")
    .run(
      tokenHash(token),
      identity.subject,
      identity.email,
      identity.name,
      identity.accountId ?? null,
      identity.password ? credentialStamp(identity.password) : null,
      Date.now() + 600000,
    );
  (await cookies()).set(cookieName, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 600,
  });
}
export async function pendingKakaoRegistration(): Promise<Pending | null> {
  const token = (await cookies()).get(cookieName)?.value;
  if (!token || !/^[a-f0-9]{64}$/.test(token)) return null;
  return (
    (table()
      .prepare(
        "SELECT * FROM kakao_registration WHERE token_hash=? AND used_at IS NULL AND expires>?",
      )
      .get(tokenHash(token), Date.now()) as Pending | undefined) ?? null
  );
}
export async function cancelKakaoRegistration() {
  const token = (await cookies()).get(cookieName)?.value;
  if (token && /^[a-f0-9]{64}$/.test(token))
    table()
      .prepare("DELETE FROM kakao_registration WHERE token_hash=?")
      .run(tokenHash(token));
  (await cookies()).delete(cookieName);
}
export async function finishKakaoRegistration(input: {
  email: string;
  password: string;
  name: string;
  age?: number | null;
  school?: string;
  major?: string;
}) {
  const pending = await pendingKakaoRegistration();
  if (!pending)
    throw new Error(
      "카카오 인증이 만료됐습니다. 카카오 로그인을 다시 진행해 주세요.",
    );
  if (input.email !== pending.email)
    throw new Error("카카오에서 확인한 이메일은 변경할 수 없습니다.");
  const password = passwordHash(input.password);
  if (
    !table()
      .prepare(
        "UPDATE kakao_registration SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires>?",
      )
      .run(Date.now(), pending.token_hash, Date.now()).changes
  )
    throw new Error(
      "이미 처리된 가입 요청입니다. 카카오 로그인을 다시 진행해 주세요.",
    );
  if (pending.account_id) {
    const account = await kakaoAccount(pending.subject);
    if (
      !account ||
      account.id !== pending.account_id ||
      account.email !== pending.email ||
      account.passwordSet ||
      credentialStamp(account.password) !== pending.credential_stamp
    )
      throw new Error(
        "회원 정보가 변경됐습니다. 카카오 로그인을 다시 진행해 주세요.",
      );
    const updated = await changeAccountPassword(account, password);
    await cancelKakaoRegistration();
    return updated;
  }
  if (await accountByEmail(pending.email))
    throw new Error("이미 가입된 이메일입니다. 기존 계정으로 로그인해 주세요.");
  const account = await createKakaoAccount(
    {
      id: randomUUID(),
      email: pending.email,
      name: input.name,
      password,
      age: input.age,
      school: input.school,
      major: input.major,
    },
    pending.subject,
  );
  await cancelKakaoRegistration();
  return account;
}
