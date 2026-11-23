import { isGuest, user } from "@/lib/server/store";
import { postingLevels } from "@/lib/server/posting-levels";

export const runtime = "nodejs";
export async function GET(request: Request) {
  const headers = { "Cache-Control": "private, no-store" };
  const current = await user();
  if (!current || isGuest(current.id))
    return Response.json(
      { error: "로그인이 필요합니다." },
      { status: 401, headers },
    );
  const params = new URL(request.url).searchParams;
  const jobId = params.get("jobId"),
    version = params.get("version");
  if (!jobId || jobId.length > 200 || !version || version.length > 160)
    return Response.json(
      { error: "공고와 분류 버전을 확인해 주세요." },
      { status: 400, headers },
    );
  try {
    const result = await postingLevels(current.id, jobId, version);
    if (!result)
      return Response.json(
        { error: "사용자 LV 저장소 미연결" },
        { status: 503, headers },
      );
    return Response.json(result, { headers });
  } catch {
    return Response.json(
      { error: "저장된 사용자 LV를 불러오지 못했습니다." },
      { status: 502, headers },
    );
  }
}
