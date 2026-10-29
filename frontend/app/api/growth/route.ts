import { randomUUID } from "node:crypto";
import { z } from "zod";
import {
  db,
  requireUser,
  workspace,
  originCheck,
  jsonBody,
  failure,
} from "@/lib/server/store";
import { emptyGrowth, type GrowthState } from "@/types/growth";
import { criteria } from "@/lib/growth/catalog";
import { mergeReviews } from "@/lib/growth/model";
import { currentFindings } from "@/lib/workspace-selectors";
export const runtime = "nodejs";
function connection() {
  const d = db();
  d.exec(
    "CREATE TABLE IF NOT EXISTS growth(user_id TEXT PRIMARY KEY,data TEXT NOT NULL)",
  );
  return d;
}
function read(id: string): GrowthState {
  const r = connection()
    .prepare("SELECT data FROM growth WHERE user_id=?")
    .get(id) as { data: string } | undefined;
  if (!r) return structuredClone(emptyGrowth);
  const { reviews = [], tasks = [] } = JSON.parse(r.data) as GrowthState;
  return { reviews, tasks };
}
const inputSchema = z.discriminatedUnion("action", [
  z.object({
    action: z.literal("review"),
    skill: z.string().max(80),
    name: z.string().max(80),
    status: z.enum(["confirmed", "edited", "excluded", "appeal"]),
  }),
  z.object({
    action: z.literal("start"),
    skill: z.string().max(80),
    level: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  }),
  z.object({
    action: z.literal("submit"),
    id: z.string(),
    evidence: z.string().min(5).max(2000),
    explanation: z.string().min(10).max(10000),
  }),
  z.object({
    action: z.literal("date"),
    id: z.string(),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  }),
]);
export async function GET() {
  try {
    const u = await requireUser();
    const g = mergeReviews(read(u.id), currentFindings(workspace(u.id)));
    return Response.json(
      { growth: g },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (e) {
    return failure(e);
  }
}
export async function POST(req: Request) {
  try {
    originCheck(req);
    const u = await requireUser();
    const input = inputSchema.parse(await jsonBody(req));
    const d = connection();
    d.exec("BEGIN IMMEDIATE");
    try {
      const g = mergeReviews(read(u.id), currentFindings(workspace(u.id)));
      if (input.action === "review") {
        const r = g.reviews.find((r) => r.skill === input.skill);
        if (!r) throw Error("결과를 다시 불러와 주세요.");
        r.status = input.status;
        if (input.status === "edited") {
          if (!criteria[input.name])
            throw Error("목록에서 기술을 선택해 주세요.");
          r.skill = input.name;
          r.level = null;
          r.reason = "이름을 수정했어요. 수준은 추가 근거가 필요해요.";
        }
      }
      if (input.action === "start") {
        if (!criteria[input.skill]) throw Error("평가 기준 준비 중이에요.");
        const r = g.reviews.find(
          (r) => r.skill === input.skill && r.status !== "excluded",
        );
        const level = r?.level || 0;
        if (input.level !== level + 1)
          throw Error("다음 단계부터 시작해 주세요.");
        if (
          !g.tasks.some(
            (t) => t.skill === input.skill && t.level === input.level,
          )
        )
          g.tasks.push({
            id: randomUUID(),
            skill: input.skill,
            level: input.level,
            baseline: r?.level || null,
            baselineEvidence: currentFindings(workspace(u.id)).map((f) => f.id),
            startedAt: new Date().toISOString(),
            date: "",
            status: "active",
            submissions: [],
          });
      }
      if (input.action === "submit") {
        const t = g.tasks.find((t) => t.id === input.id);
        if (!t || t.status === "completed")
          throw Error("제출할 과제를 찾을 수 없어요.");
        t.status = "needs_evidence";
        t.submissions.push({
          at: new Date().toISOString(),
          evidence: input.evidence,
          explanation: input.explanation,
          feedback: "저장했어요. 검토 기능은 준비 중이에요.",
        });
      }
      if (input.action === "date") {
        const t = g.tasks.find((t) => t.id === input.id);
        if (t) t.date = input.date;
      }
      d.prepare(
        "INSERT INTO growth VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
      ).run(u.id, JSON.stringify(g));
      d.exec("COMMIT");
      return Response.json({ growth: g });
    } catch (e) {
      d.exec("ROLLBACK");
      throw e;
    }
  } catch (e) {
    return failure(e);
  }
}
