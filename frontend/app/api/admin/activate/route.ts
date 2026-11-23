import { createHash } from "node:crypto";
import { z } from "zod";
import {
  db,
  originCheck,
  jsonBody,
  passwordHash,
  session,
  rateLimit,
} from "@/lib/server/store";
import { memberRole } from "@/lib/server/notices";
export const runtime = "nodejs";
export async function POST(request: Request) {
  try {
    originCheck(request);
  } catch {
    return Response.json(
      { error: "요청 출처를 확인해 주세요." },
      { status: 403 },
    );
  }
  try {
    rateLimit("admin-activation", 30);
    const input = z
      .object({
        token: z.string().regex(/^[a-f0-9]{64}$/),
        password: z.string().min(10).max(128),
      })
      .parse(await jsonBody(request));
    const hash = createHash("sha256").update(input.token).digest("hex");
    const d = db(),
      invite = d
        .prepare(
          "SELECT user_id FROM admin_invitations WHERE token_hash=? AND expires>? AND used_at IS NULL",
        )
        .get(hash, Date.now()) as { user_id: string } | undefined;
    if (!invite || (await memberRole(invite.user_id)) !== "ADMIN")
      return Response.json(
        { error: "설정 링크가 만료되었거나 올바르지 않습니다." },
        { status: 400 },
      );
    const password = passwordHash(input.password);
    d.exec("BEGIN IMMEDIATE");
    try {
      const updated = d
        .prepare(
          "UPDATE admin_invitations SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires>?",
        )
        .run(Date.now(), hash, Date.now());
      if (!updated.changes) throw new Error("Invitation used");
      d.prepare("UPDATE users SET password=? WHERE id=?").run(
        password,
        invite.user_id,
      );
      d.prepare("DELETE FROM sessions WHERE user_id=?").run(invite.user_id);
      d.exec("COMMIT");
    } catch (error) {
      d.exec("ROLLBACK");
      throw error;
    }
    await session(invite.user_id);
    return Response.json(
      { ok: true },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json(
      {
        error:
          "설정 링크와 비밀번호를 확인해 주세요. 비밀번호는 10자 이상이어야 합니다.",
      },
      { status: 400 },
    );
  }
}
