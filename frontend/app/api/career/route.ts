import {
  requireUser,
  isGuest,
  workspace,
  saveWorkspace,
  originCheck,
  jsonBody,
  failure,
} from "@/lib/server/store";
import { mutation } from "@/lib/server/schema";
export const runtime = "nodejs";
export async function GET() {
  try {
    const u = await requireUser();
    return Response.json(
      { user: u, guest: isGuest(u.id), workspace: workspace(u.id) },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json({ error: "로그인이 필요합니다." }, { status: 401 });
  }
}
export async function POST(req: Request) {
  try {
    originCheck(req);
    const u = await requireUser();
    const input = mutation.parse(await jsonBody(req));
    const state = workspace(u.id);
    const { action, ...patch } = input;
    void action;
    const next = { ...state, ...patch };
    saveWorkspace(u.id, next);
    return Response.json({ workspace: next });
  } catch (e) {
    return failure(e);
  }
}
