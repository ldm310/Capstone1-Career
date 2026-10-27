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
export const runtime = "nodejs";
export async function GET() {
  const current = (await user()) || null;
  return Response.json(
    { user: current, guest: current ? isGuest(current.id) : false },
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
