import { isGuest, user } from "@/lib/server/store";
import { demoAccount } from "@/lib/server/demo-account";
import { lvStatEnabled } from "@/lib/server/lv-stat";
import { postingLevels } from "@/lib/server/posting-levels";
import {
  KeywordsStatusError,
  profilePostingLevels,
} from "@/lib/server/profile-levels";

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
    // 스테이징 스위치가 꺼진 서버(운영)와 데모 계정은 결과 파일을 읽지 않는다. 데모 계정은 누구나 같이 쓰는
    // 로그인이라서다(결과는 분석을 요청한 사람에게만 보인다).
    const fromProfile =
      !lvStatEnabled() || current.email === demoAccount.email
        ? null
        : await profilePostingLevels(current.id, jobId, version);
    const result =
      fromProfile ?? (await postingLevels(current.id, jobId, version));
    if (!result)
      return Response.json(
        { error: "사용자 LV 저장소 미연결" },
        { status: 503, headers },
      );
    return Response.json(result, { headers });
  } catch (error) {
    // 답(상태·본문·헤더)은 그대로 두고 서버 기록만 남긴다(job-keywords.ts와 같은 꼴).
    console.error("My levels lookup failed", {
      jobId,
      error: loggedError(error),
    });
    return Response.json(
      { error: "저장된 사용자 LV를 불러오지 못했습니다." },
      { status: 502, headers },
    );
  }
}

// 서버 기록에 남길 오류. 글(message)은 공고 문장 응답 상태만 담은 KeywordsStatusError만 남기고, 그 밖의 오류는
// 이름만 남긴다. 결과 파일 읽기 오류(EACCES·EISDIR 등)의 글에는 파일 경로가, DB 연결 오류의 글에는 DB 주소가 들어간다.
function loggedError(error: unknown) {
  if (error instanceof KeywordsStatusError)
    return `${error.name}: ${error.message}`;
  return error instanceof Error ? error.name : "UnknownError";
}
