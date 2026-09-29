import { randomBytes, randomUUID } from "node:crypto";
import {
  db,
  user,
  session,
  workspace,
  originCheck,
  rateLimit,
  passwordHash,
  failure,
  isGuest,
} from "@/lib/server/store";
export const runtime = "nodejs";
// Establish an isolated browser session; never relax ownership checks on data APIs.
export async function POST(req: Request) {
  try {
    originCheck(req);
    let current = await user();
    if (!current) {
      rateLimit("guest:create", 120);
      const id = randomUUID();
      const connection = db();
      connection
        .prepare("INSERT INTO users VALUES(?,?,?,?)")
        .run(
          id,
          `${id}@guest.career.invalid`,
          "방문자",
          passwordHash(randomBytes(32).toString("hex")),
        );
      connection.prepare("INSERT INTO guests(user_id) VALUES(?)").run(id);
      await session(id);
      current = await user();
    }
    if (!current)
      throw new Error(
        "게스트 공간을 열지 못했어요. 쿠키를 허용한 뒤 다시 시도해 주세요.",
      );
    return Response.json(
      {
        user: current,
        guest: isGuest(current.id),
        workspace: workspace(current.id),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (e) {
    return failure(e);
  }
}
