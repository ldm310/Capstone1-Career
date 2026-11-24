import { backendUrl } from "@/lib/server/backend-jobs";

export const runtime = "nodejs";

// 브라우저는 같은 출처를 호출하고 Spring 주소는 서버 환경변수에서만 읽는다.
export async function GET() {
  const base = backendUrl();
  if (!base)
    return Response.json(
      { error: "카테고리 조회 서버가 설정되지 않았어요." },
      { status: 503 },
    );
  try {
    const response = await fetch(`${base}/api/skill-categories`, {
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Category backend unavailable");
    return Response.json(await response.json(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      { error: "카테고리를 불러오지 못했어요." },
      { status: 502 },
    );
  }
}
