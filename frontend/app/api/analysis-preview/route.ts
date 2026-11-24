import { createHash, randomUUID } from "node:crypto";
import { z } from "zod";
import {
  user,
  isGuest,
  originCheck,
  jsonBody,
  workspace,
  saveWorkspace,
  rateLimit,
} from "@/lib/server/store";
import { noticeDatabase, profileNamespace } from "@/lib/server/notices";
import examples from "@/mock/reviewed-keyword-examples.json";
export const runtime = "nodejs";
export async function POST(request: Request) {
  const current = await user();
  if (!current || isGuest(current.id))
    return Response.json({ error: "로그인이 필요합니다." }, { status: 401 });
  try {
    originCheck(request);
  } catch {
    return Response.json(
      { error: "요청 출처를 확인해 주세요." },
      { status: 403 },
    );
  }
  try {
    rateLimit("analysis-preview:" + current.id, 20);
    const input = z
      .object({ url: z.string().max(2000) })
      .parse(await jsonBody(request));
    const url = new URL(input.url);
    if (
      url.protocol !== "https:" ||
      url.hostname !== "github.com" ||
      url.username ||
      url.password ||
      url.port ||
      !/^\/[\w.-]+\/[\w.-]+\/?$/.test(url.pathname)
    )
      return Response.json(
        { error: "GitHub 저장소 형식의 링크를 입력해 주세요." },
        { status: 400 },
      );
    const db = noticeDatabase(),
      client = await db.connect(),
      namespace = profileNamespace();
    const sourceId =
        "preview-github-" +
        createHash("sha256")
          .update((url.origin + url.pathname.replace(/\/$/, "")).toLowerCase())
          .digest("hex")
          .slice(0, 20),
      at = new Date().toISOString();
    try {
      await client.query("BEGIN");
      const fixture = await client.query(
        "SELECT 1 FROM public.career_lv_posting_keyword_level WHERE namespace=$1 AND subject_id='demo-user' AND evaluation_kind='DEMO' LIMIT 1",
        [namespace],
      );
      if (!fixture.rowCount) throw new Error("Preview data unavailable");
      await client.query(
        `INSERT INTO public.career_lv_member(namespace,subject_id,preview_enabled) VALUES($1,$2,true) ON CONFLICT(namespace,subject_id) DO UPDATE SET preview_enabled=true`,
        [namespace, current.id],
      );
      await client.query(
        `INSERT INTO public.career_lv_analysis_source(namespace,subject_id,source_id,kind,title,locator,is_simulated) VALUES($1,$2,$3,'GITHUB',$4,$5,true) ON CONFLICT(namespace,subject_id,source_id) DO UPDATE SET title=excluded.title,locator=excluded.locator`,
        [
          namespace,
          current.id,
          sourceId,
          url.pathname.slice(1),
          url.toString(),
        ],
      );
      if (current.id !== "demo-user")
        await client.query(
          `INSERT INTO public.career_lv_posting_keyword_level(namespace,subject_id,job_id,keyword_id,taxonomy_version,keyword_text,category_codes,score,reference_score,reference_kind,evidence_source_ids,evaluation_kind,method_version)
        SELECT namespace,$2,job_id,keyword_id,taxonomy_version,keyword_text,category_codes,score,reference_score,reference_kind,ARRAY[$3]::text[],'DEMO','preview-fixture-v1'
        FROM public.career_lv_posting_keyword_level WHERE namespace=$1 AND subject_id='demo-user' AND evaluation_kind='DEMO' ON CONFLICT DO NOTHING`,
          [namespace, current.id, sourceId],
        );
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
    const state = workspace(current.id);
    state.runs = [
      {
        id: randomUUID(),
        sourceId: `preview:${sourceId}`,
        title: url.pathname.slice(1),
        at,
        simulated: true,
        findings: examples.examples.map((keyword) => ({
          id: randomUUID(),
          skill: keyword.text,
          title: url.pathname.slice(1),
          type: "implementation" as const,
          quote: keyword.text,
          url: url.toString(),
          detectedAt: at,
        })),
      },
      ...state.runs.filter((run) => run.sourceId !== `preview:${sourceId}`),
    ].slice(0, 30);
    saveWorkspace(current.id, state);
    return Response.json(
      { workspace: state, simulation: true },
      { headers: { "Cache-Control": "private, no-store" } },
    );
  } catch (error) {
    return Response.json(
      {
        error:
          error instanceof z.ZodError || error instanceof TypeError
            ? "링크를 확인해 주세요."
            : "미리보기 결과를 준비하지 못했습니다.",
      },
      {
        status:
          error instanceof z.ZodError || error instanceof TypeError ? 400 : 503,
      },
    );
  }
}
