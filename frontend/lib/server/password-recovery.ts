import "server-only";
import { createHash, randomBytes } from "node:crypto";
import { db, credentialStamp, passwordHash } from "./store";
import { accountByEmail, accountById, changeAccountPassword } from "./accounts";
import { sendRecoveryMail } from "./recovery-mail";

const hash = (value: string) =>
  createHash("sha256").update(value).digest("hex");
function table() {
  const connection = db();
  connection.exec(
    `CREATE TABLE IF NOT EXISTS password_reset_tokens(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,email TEXT NOT NULL,credential_stamp TEXT NOT NULL,expires INTEGER NOT NULL,used_at INTEGER)`,
  );
  return connection;
}
export async function requestPasswordRecovery(email: string) {
  const account = await accountByEmail(email);
  if (!account || account.email === "demo@career.dev") return;
  const token = randomBytes(32).toString("hex");
  const connection = table();
  connection
    .prepare(
      "DELETE FROM password_reset_tokens WHERE expires<? OR used_at IS NOT NULL",
    )
    .run(Date.now());
  connection
    .prepare("INSERT INTO password_reset_tokens VALUES(?,?,?,?,?,NULL)")
    .run(
      hash(token),
      account.id,
      account.email,
      credentialStamp(account.password),
      Date.now() + 1800000,
    );
  try {
    await sendRecoveryMail(account.email, token);
  } catch (error) {
    connection
      .prepare("DELETE FROM password_reset_tokens WHERE token_hash=?")
      .run(hash(token));
    throw error;
  }
}
export async function completePasswordRecovery(
  token: string,
  password: string,
) {
  const connection = table();
  const ticket = connection
    .prepare(
      "SELECT * FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires>?",
    )
    .get(hash(token), Date.now()) as
    | {
        token_hash: string;
        user_id: string;
        email: string;
        credential_stamp: string;
      }
    | undefined;
  if (!ticket)
    throw new Error(
      "재설정 링크가 만료됐거나 이미 사용됐습니다. 새 링크를 요청해 주세요.",
    );
  const account = await accountById(ticket.user_id);
  if (
    !account ||
    account.email !== ticket.email ||
    credentialStamp(account.password) !== ticket.credential_stamp ||
    account.email === "demo@career.dev"
  )
    throw new Error(
      "재설정 링크가 만료됐거나 이미 사용됐습니다. 새 링크를 요청해 주세요.",
    );
  const passwordValue = passwordHash(password);
  if (
    !connection
      .prepare(
        "UPDATE password_reset_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires>?",
      )
      .run(Date.now(), ticket.token_hash, Date.now()).changes
  )
    throw new Error("이미 처리된 재설정 요청입니다. 새 링크를 요청해 주세요.");
  await changeAccountPassword(account, passwordValue);
  connection
    .prepare(
      "UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL",
    )
    .run(Date.now(), account.id);
}
