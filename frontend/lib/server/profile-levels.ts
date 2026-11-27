import "server-only";
import { scoreKeyword } from "@/lib/lv-stat/score";
import { jobKeywords } from "@/lib/server/job-keywords";
import { readProfile } from "@/lib/server/lv-stat";
import { profileNamespace } from "@/lib/server/notices";
import type { PostingLevels, SavedPostingLevel } from "@/types/posting-level";

// 스테이징 LV 서비스: 로그인한 사람의 분석 결과(lv-stat/service/CONTRACT.md의 profile)로 공고 문장마다 점수를
// 그 자리에서 계산해 저장된 LV(RDS)와 같은 모양으로 준다. DB에는 쓰지 않는다. 결과 파일이 없으면 null이다.
// The caller supplies only the authenticated session subject, never a query userId.
export async function profilePostingLevels(
  subject: string,
  jobId: string,
  version: string,
): Promise<PostingLevels | null> {
  const profile = await readProfile(profileNamespace(), subject);
  if (!profile) return null;
  const { status, body } = await jobKeywords(jobId);
  if (status !== 200 || "error" in body)
    throw new Error(`공고 문장 응답 ${status}`);
  const levels: SavedPostingLevel[] = [];
  // 분류 버전이 화면이 물은 것과 다르면(문장 쪽 버전이 없거나 null이어도) 행이 없다.
  if (body.version === version)
    for (const keyword of body.keywords) {
      // 화면은 keywordId·text·정렬한 categoryCodes가 모두 같은 행만 문장에 맞춘다. 그래서 글이 없는 문장은
      // 행을 만들지 않고, categoryCodes는 문장 그대로 둔다(같은 코드 두 번, 재지 않는 Q·S·H 포함).
      if (typeof keyword.text !== "string") continue;
      const { score } = scoreKeyword(profile, keyword);
      if (score === null) continue;
      levels.push({
        keywordId: keyword.id,
        text: keyword.text,
        categoryCodes: keyword.categoryCodes,
        score,
        referenceScore: null,
        referenceKind: null,
        evaluationKind: "CONFIRMED",
        evaluatedAt: profile.analyzedAt,
      });
    }
  return {
    jobId,
    taxonomyVersion: version,
    source: "LV_STAT",
    levels,
    sources: [
      {
        id: `lv-stat:${profile.login}`,
        kind: "GITHUB",
        title: profile.login,
        simulated: false,
      },
    ],
    labels: profile.labels,
    identityVerified: false,
    methodVersion: profile.method,
  };
}
