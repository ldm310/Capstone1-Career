import { isGuest, user } from "@/lib/server/store";
import { postingLevels } from "@/lib/server/posting-levels";
import { profilePostingLevels } from "@/lib/server/profile-levels";

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
    // 분석 결과 파일(스테이징 LV 서비스)이 있으면 그것으로 계산하고, 없으면 지금처럼 저장된 LV(RDS)를 읽는다.
    const result =
      (await profilePostingLevels(current.id, jobId, version)) ??
      (await postingLevels(current.id, jobId, version));
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
