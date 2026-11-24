import "server-only";
import nodemailer from "nodemailer";
import { mkdirSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import path from "node:path";

export function recoveryMailSettings() {
  const value = process.env.CAREER_PUBLIC_URL;
  if (!value) throw new Error("MAIL_NOT_CONFIGURED");
  const base = new URL(value);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(base.hostname);
  if (
    base.username ||
    base.password ||
    base.search ||
    base.hash ||
    base.pathname !== "/" ||
    !(base.protocol === "https:" || (base.protocol === "http:" && local))
  )
    throw new Error("MAIL_NOT_CONFIGURED");
  const mode = process.env.CAREER_MAIL_TRANSPORT;
  if (mode === "file" && local)
    return { mode: "file" as const, origin: base.origin };
  if (
    mode === "smtp" &&
    process.env.CAREER_SMTP_HOST &&
    process.env.CAREER_SMTP_USER &&
    process.env.CAREER_SMTP_PASSWORD &&
    process.env.CAREER_MAIL_FROM
  )
    return { mode: "smtp" as const, origin: base.origin };
  throw new Error("MAIL_NOT_CONFIGURED");
}
export async function sendRecoveryMail(email: string, token: string) {
  const settings = recoveryMailSettings();
  const link = new URL("/reset-password", settings.origin);
  link.hash = "token=" + token;
  const subject = "Career 비밀번호 재설정";
  const text = `Career 비밀번호 재설정\n\n다음 링크에서 새 비밀번호를 설정해 주세요.\n${link.href}\n\n이 링크는 30분 동안 한 번만 사용할 수 있습니다. 요청한 적이 없다면 이 메일을 무시해 주세요.`;
  const html = `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>${subject}</title><body style="font-family:sans-serif;color:#233f52;max-width:600px;margin:60px auto;padding:24px;line-height:1.8"><h1>${subject}</h1><p>아래 버튼에서 새 비밀번호를 설정해 주세요.</p><p><a style="display:inline-block;background:#315a7b;color:white;padding:12px 20px;border-radius:8px;text-decoration:none" href="${link.href}">비밀번호 재설정</a></p><p>이 링크는 30분 동안 한 번만 사용할 수 있습니다.</p><p>요청한 적이 없다면 이 메일을 무시해 주세요.</p></body></html>`;
  await sendCareerMail(email, subject, text, html);
}
export async function sendCareerMail(
  email: string,
  subject: string,
  text: string,
  html: string,
) {
  const settings = recoveryMailSettings();
  if (settings.mode === "file") {
    const directory = path.join(
      process.env.CAREER_DATA_DIR || path.join(process.cwd(), ".career-data"),
      "mailbox",
    );
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    const name = Date.now() + "-" + randomUUID();
    writeFileSync(
      path.join(directory, name + ".json"),
      JSON.stringify({ to: email, subject, text, html }, null, 2),
      { mode: 0o600 },
    );
    writeFileSync(path.join(directory, name + ".html"), html, { mode: 0o600 });
    return;
  }
  const port = Number(process.env.CAREER_SMTP_PORT || 587);
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error("MAIL_NOT_CONFIGURED");
  const transport = nodemailer.createTransport({
    host: process.env.CAREER_SMTP_HOST,
    port,
    secure: port === 465,
    requireTLS: port !== 465,
    auth: {
      user: process.env.CAREER_SMTP_USER,
      pass: process.env.CAREER_SMTP_PASSWORD,
    },
    connectionTimeout: 10000,
    greetingTimeout: 10000,
    socketTimeout: 15000,
    disableFileAccess: true,
    disableUrlAccess: true,
  });
  await transport.sendMail({
    from: process.env.CAREER_MAIL_FROM,
    to: email,
    subject,
    text,
    html,
  });
}
