import "server-only";
import { createHash, randomBytes } from "node:crypto";
import { db } from "./store";
import { accountById } from "./accounts";
import { recoveryMailSettings, sendCareerMail } from "./recovery-mail";

const digest = (value: string) =>
  createHash("sha256").update(value).digest("hex");
function table() {
  const connection = db();
  connection.exec(`CREATE TABLE IF NOT EXISTS email_verifications(
    token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,email TEXT NOT NULL,
    expires INTEGER NOT NULL,verified_at INTEGER)`);
  return connection;
}
export function verifiedEmail(userId: string, email: string) {
  return !!table()
    .prepare(
      "SELECT 1 FROM email_verifications WHERE user_id=? AND email=? AND verified_at IS NOT NULL LIMIT 1",
    )
    .get(userId, email);
}
export async function requestEmailVerification(userId: string) {
  const settings = recoveryMailSettings();
  const account = await accountById(userId);
  if (!account || account.email === "demo@career.dev")
    throw new Error("회원 계정으로 로그인해 주세요.");
  const token = randomBytes(32).toString("hex");
  const link = new URL("/verify-email", settings.origin);
  link.hash = "token=" + token;
  table()
    .prepare(
      "DELETE FROM email_verifications WHERE expires<? AND verified_at IS NULL",
    )
    .run(Date.now());
  table()
    .prepare("INSERT INTO email_verifications VALUES(?,?,?,?,NULL)")
    .run(digest(token), account.id, account.email, Date.now() + 1800000);
  const subject = "Career 이메일 인증";
  const text = `Career 이메일 인증\n\n아래 링크를 눌러 이메일을 인증해 주세요.\n${link.href}\n\n30분 동안 한 번만 사용할 수 있습니다. 이번 인증은 로그인이나 회원가입의 필수 조건이 아닙니다. 요청하지 않았다면 무시해 주세요.`;
  const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>${subject}</title></head><body style="margin:0;background:#f3f6fa;font-family:Arial,sans-serif;color:#203d52"><table role="presentation" style="width:100%;padding:40px 16px"><tr><td><table role="presentation" style="width:100%;max-width:560px;margin:auto;background:white;border:1px solid #dbe5ed;border-radius:16px;padding:32px"><tr><td><p style="font-size:24px;font-weight:bold;margin:0 0 32px">Career</p><h1 style="font-size:24px;margin:0 0 20px">이메일 인증</h1><p style="line-height:1.8">아래 버튼을 눌러 이메일 인증을 완료해 주세요.</p><p style="margin:28px 0"><a href="${link.href}" style="display:inline-block;background:#315a7b;color:white;text-decoration:none;padding:14px 24px;border-radius:8px;font-weight:bold">이메일 인증하기</a></p><p style="font-size:14px;line-height:1.8;color:#526d82">유효시간 30분, 한 번만 사용할 수 있습니다.<br>이번 인증은 로그인이나 회원가입의 필수 조건이 아닙니다.<br>요청하지 않았다면 이 메일을 무시해 주세요.</p></td></tr></table></td></tr></table></body></html>`;
  try {
    await sendCareerMail(account.email, subject, text, html);
  } catch (error) {
    table()
      .prepare("DELETE FROM email_verifications WHERE token_hash=?")
      .run(digest(token));
    throw error;
  }
}
export async function confirmEmailVerification(token: string) {
  const ticket = table()
    .prepare(
      "SELECT * FROM email_verifications WHERE token_hash=? AND verified_at IS NULL AND expires>?",
    )
    .get(digest(token), Date.now()) as
    { user_id: string; email: string } | undefined;
  if (!ticket) throw new Error("인증 링크가 만료됐거나 이미 사용됐습니다.");
  const account = await accountById(ticket.user_id);
  if (!account || account.email !== ticket.email)
    throw new Error("이메일이 변경됐습니다. 인증 메일을 다시 요청해 주세요.");
  if (
    !table()
      .prepare(
        "UPDATE email_verifications SET verified_at=? WHERE token_hash=? AND verified_at IS NULL AND expires>?",
      )
      .run(Date.now(), digest(token), Date.now()).changes
  )
    throw new Error("인증 링크가 만료됐거나 이미 사용됐습니다.");
}
