import { randomUUID } from "node:crypto";
import { z } from "zod";
import {
  db,
  user,
  session,
  logout,
  passwordHash,
  passwordMatches,
  originCheck,
  rateLimit,
  jsonBody,
  failure,
  isGuest,
} from "@/lib/server/store";
import { demoAccount, ensureDemoAccount } from "@/lib/server/demo-account";
import { profile, profileSchema, saveProfile } from "@/lib/server/user-data";
export const runtime = "nodejs";
export async function GET() {
  const current = (await user()) || null;
  const guest = current ? isGuest(current.id) : false;
  return Response.json(
    {
      user: current,
      guest,
      profile: current && !guest ? profile(current.id) : null,
      demo: current?.email === demoAccount.email,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
export async function POST(req: Request) {
  try {
    originCheck(req);
    const body = await jsonBody(req);
    if (body.action === "logout") {
      await logout();
      return Response.json({ ok: true });
    }
    if (body.action === "update" || body.action === "password")
      return await updateAccount(body);
    rateLimit("auth:server", 150);
    const input = z
      .object({
        action: z.enum(["login", "register"]),
        email: z.email().max(200),
        password: z.string().min(10).max(128),
        name: z.string().trim().min(1).max(60).optional(),
      })
      .parse(body);
    const email = input.email.toLowerCase();
    rateLimit("auth:" + email);
    if (email === demoAccount.email) ensureDemoAccount();
    const found = db()
      .prepare("SELECT * FROM users WHERE email=?")
      .get(email) as { id: string; password: string } | undefined;
    if (input.action === "register") {
      if (found)
        throw new Error(
          "이 이메일로 계정을 만들 수 없습니다. 로그인해 주세요.",
        );
      const id = randomUUID();
      db()
        .prepare("INSERT INTO users VALUES(?,?,?,?)")
        .run(id, email, input.name || "사용자", passwordHash(input.password));
      await session(id);
    } else {
      if (!found || !passwordMatches(input.password, found.password))
        throw new Error("이메일 또는 비밀번호를 확인하세요.");
      await session(found.id);
    }
    return Response.json({ user: await user() });
  } catch (e) {
    return failure(e);
  }
}

// 마이페이지의 내 정보 수정, 비밀번호 변경. 게스트는 수정할 수 없다.
async function updateAccount(body: Record<string, unknown>) {
  const current = await user();
  if (!current || isGuest(current.id))
    throw new Error("로그인한 계정만 수정할 수 있어요.");
  rateLimit("account:" + current.id, 60);
  if (body.action === "password") {
    const input = z
      .object({
        current: z.string().min(1).max(128),
        next: z
          .string()
          .min(10, "새 비밀번호는 10자 이상이어야 해요.")
          .max(128),
      })
      .parse(body);
    if (current.email === demoAccount.email)
      throw new Error("데모 계정은 비밀번호를 바꿀 수 없어요.");
    const row = db()
      .prepare("SELECT password FROM users WHERE id=?")
      .get(current.id) as { password: string };
    if (!passwordMatches(input.current, row.password))
      throw new Error("현재 비밀번호가 맞지 않아요.");
    db()
      .prepare("UPDATE users SET password=? WHERE id=?")
      .run(passwordHash(input.next), current.id);
    return Response.json({ ok: true });
  }
  const input = z
    .object({
      name: z.string().trim().min(1, "이름을 입력해 주세요.").max(60),
      email: z.email("이메일 형식을 확인해 주세요.").max(200),
      profile: profileSchema,
    })
    .parse(body);
  const email = input.email.toLowerCase();
  if (email !== current.email) {
    if (current.email === demoAccount.email)
      throw new Error("데모 계정은 이메일을 바꿀 수 없어요.");
    if (db().prepare("SELECT id FROM users WHERE email=?").get(email))
      throw new Error("이미 사용 중인 이메일이에요.");
  }
  db()
    .prepare("UPDATE users SET name=?, email=? WHERE id=?")
    .run(input.name, email, current.id);
  saveProfile(current.id, input.profile);
  return Response.json({ user: await user(), profile: input.profile });
}
