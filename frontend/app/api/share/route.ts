import { randomBytes } from "node:crypto";
import { z } from "zod";
import {
  db,
  requireUser,
  workspace,
  originCheck,
  jsonBody,
  failure,
} from "@/lib/server/store";
export const runtime = "nodejs";
export async function GET() {
  try {
    const u = await requireUser();
    return Response.json({
      shares: db()
        .prepare("SELECT token FROM shares WHERE user_id=?")
        .all(u.id),
    });
  } catch {
    return Response.json({ error: "로그인이 필요합니다." }, { status: 401 });
  }
}
export async function POST(req: Request) {
  try {
    originCheck(req);
    const u = await requireUser();
    const input = z
      .object({ ids: z.array(z.string()).max(100) })
      .parse(await jsonBody(req));
    const state = workspace(u.id);
    const findings = state.runs
      .flatMap((r) => r.findings)
      .filter((f) => input.ids.includes(f.id))
      .map((f) => ({
        skill: f.skill,
        type: f.type,
        title: f.title,
        quote: f.quote,
        url: f.url.startsWith("https://github.com/") ? f.url : "",
      }));
    if (!findings.length) throw new Error("공개할 근거를 선택하세요.");
    const token = randomBytes(24).toString("hex");
    db()
      .prepare("INSERT INTO shares VALUES(?,?,?)")
      .run(
        token,
        u.id,
        JSON.stringify({
          name: u.name,
          findings,
          at: new Date().toISOString(),
        }),
      );
    return Response.json({ url: `/share/${token}` });
  } catch (e) {
    return failure(e);
  }
}
export async function DELETE(req: Request) {
  try {
    originCheck(req);
    const u = await requireUser();
    const body = await jsonBody(req);
    db()
      .prepare("DELETE FROM shares WHERE token=? AND user_id=?")
      .run(String(body.token), u.id);
    return Response.json({ ok: true });
  } catch (e) {
    return failure(e);
  }
}
