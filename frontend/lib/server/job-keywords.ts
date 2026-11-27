import type { PostingKeyword } from "@/lib/job-evidence";
import { backendUrl } from "@/lib/server/backend-jobs";
import { skillCategories } from "@/lib/skill-categories";
import examples from "@/mock/reviewed-keyword-examples.json";
import { dummyJobs } from "@/lib/dummy-jobs";
import { studyDemoJobs } from "@/lib/study-prototype";

// GET /api/jobs/keywords의 상태 코드와 본문. 라우트 밖(서버)에서도 같은 공고 문장을 쓰려고 함수로 둔다.
// "server-only"는 넣지 않는다(backend-jobs.ts와 같음). 넣으면 Next 밖(Node)에서 route를 정적 import하는 tests/job-keywords.spec.ts가 읽히지 않는다.
export type JobKeyword = PostingKeyword & { requirementType?: string };
export type JobKeywordsBody =
  | {
      source: "EXAMPLE" | "UNAVAILABLE" | "SAVED_REVIEW";
      version?: string;
      keywords: JobKeyword[];
      levelScoringEnabled: boolean;
    }
  | { error: string };

interface Item {
  itemId: number;
  text: string;
  sourceCategory: string;
  assignment: {
    status: string;
    categoryCodes: string[];
    excludedFromCounts: boolean;
    needsReview: boolean;
  };
}
export async function jobKeywords(
  jobId: string,
): Promise<{ status: number; body: JobKeywordsBody }> {
  if (!jobId || jobId.length > 200)
    return { status: 400, body: { error: "공고를 확인해 주세요." } };
  if ([...dummyJobs, ...studyDemoJobs].some((job) => job.id === jobId)) {
    return {
      status: 200,
      body: {
        source: "EXAMPLE",
        version: examples.version,
        keywords: examples.examples,
        levelScoringEnabled: false,
      },
    };
  }
  if (!/^be:[1-9]\d*$/.test(jobId))
    return {
      status: 200,
      body: {
        source: "UNAVAILABLE",
        keywords: [],
        levelScoringEnabled: false,
      },
    };
  const base = backendUrl();
  if (!base)
    return {
      status: 503,
      body: { error: "키워드 분류 서버가 연결되지 않았어요." },
    };
  try {
    const response = await fetch(
      `${base}/api/postings/${jobId.slice(3)}/skill-categories`,
      { signal: AbortSignal.timeout(5000), cache: "no-store" },
    );
    if (!response.ok)
      throw new BackendStatusError(`백엔드 응답 ${response.status}`);
    const data = await response.json();
    const codes = new Set<string>(
      skillCategories.map((category) => category.code),
    );
    const items: Item[] = data.recruitUnits.flatMap(
      (unit: { items: Item[] }) => unit.items,
    );
    const keywords = items
      .filter(
        (item) =>
          item.assignment.status === "CLASSIFIED" &&
          !item.assignment.excludedFromCounts &&
          !item.assignment.needsReview &&
          item.assignment.categoryCodes.some((code) => codes.has(code)),
      )
      .map((item) => ({
        id: String(item.itemId),
        text: item.text,
        requirementType: item.sourceCategory,
        categoryCodes: item.assignment.categoryCodes.filter((code) =>
          codes.has(code),
        ),
        level: null,
      }));
    return {
      status: 200,
      body: {
        source: "SAVED_REVIEW",
        version: data.version,
        keywords,
        levelScoringEnabled: false,
      },
    };
  } catch (error) {
    // 답(상태·본문·헤더)은 그대로 두고 서버 기록만 남긴다. 백엔드 주소·응답 본문·공고 글은 남기지 않는다.
    console.error("Job keyword lookup failed", {
      postingId: jobId.slice(3),
      error: loggedError(error),
    });
    return {
      status: 502,
      body: { error: "공고의 저장된 키워드 분류를 불러오지 못했어요." },
    };
  }
}

// 백엔드가 2xx가 아닌 상태로 답했다. 글에는 그 상태만 있어 서버 기록에 남긴다.
class BackendStatusError extends Error {}

// 서버 기록에 남길 오류. 글(message)은 위의 BackendStatusError만 남기고, fetch·JSON 해석이 던진 오류는 이름만
// 남긴다. 그 글에는 백엔드 주소(주소 해석·자격 증명 오류)나 응답 본문 일부(JSON 해석 오류)가 들어간다.
function loggedError(error: unknown) {
  if (error instanceof BackendStatusError)
    return `${error.name}: ${error.message}`;
  return error instanceof Error ? error.name : "UnknownError";
}
