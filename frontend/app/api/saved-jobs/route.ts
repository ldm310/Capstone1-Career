import { z } from "zod";
import {
  failure,
  jsonBody,
  originCheck,
  rateLimit,
  user,
} from "@/lib/server/store";
import {
  removeSavedJob,
  saveJob,
  savedJobSchema,
  savedJobs,
} from "@/lib/server/user-data";
export const runtime = "nodejs";

export async function GET() {
  const current = await user();
  if (!current)
    return Response.json({ error: "로그인이 필요합니다." }, { status: 401 });
  return Response.json(
    { jobs: savedJobs(current.id) },
    { headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(req: Request) {
  try {
    originCheck(req);
    const current = await user();
    if (!current)
      return Response.json({ error: "로그인이 필요합니다." }, { status: 401 });
    rateLimit("saved:" + current.id, 300);
    const input = z
      .discriminatedUnion("action", [
        z.object({ action: z.literal("save"), job: savedJobSchema }),
        z.object({ action: z.literal("remove"), id: z.string().max(300) }),
      ])
      .parse(await jsonBody(req));
    if (input.action === "save") {
      if (savedJobs(current.id).length >= 200)
        throw new Error("공고는 200개까지 저장할 수 있어요.");
      saveJob(current.id, input.job);
    } else removeSavedJob(current.id, input.id);
    return Response.json({ jobs: savedJobs(current.id) });
  } catch (e) {
    return failure(e);
  }
}
