import { backendUrl } from "@/lib/server/backend-jobs";
import { skillCategories } from "@/lib/skill-categories";
import examples from "@/mock/reviewed-keyword-examples.json";
import { dummyJobs } from "@/lib/dummy-jobs";
import { studyDemoJobs } from "@/lib/study-prototype";

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
export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("jobId");
  if (!id || id.length > 200)
    return Response.json({ error: "공고를 확인해 주세요." }, { status: 400 });
  if ([...dummyJobs, ...studyDemoJobs].some((job) => job.id === id)) {
    return Response.json({
      source: "EXAMPLE",
      version: examples.version,
      keywords: examples.examples,
      levelScoringEnabled: false,
    });
  }
  if (!/^be:[1-9]\d*$/.test(id))
    return Response.json({
      source: "UNAVAILABLE",
      keywords: [],
      levelScoringEnabled: false,
    });
  const base = backendUrl();
  if (!base)
    return Response.json(
      { error: "키워드 분류 서버가 연결되지 않았어요." },
      { status: 503 },
    );
  try {
    const response = await fetch(
      `${base}/api/postings/${id.slice(3)}/skill-categories`,
      { signal: AbortSignal.timeout(5000), cache: "no-store" },
    );
    if (!response.ok) throw new Error();
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
    return Response.json({
      source: "SAVED_REVIEW",
      version: data.version,
      keywords,
      levelScoringEnabled: false,
    });
  } catch {
    return Response.json(
      { error: "공고의 저장된 키워드 분류를 불러오지 못했어요." },
      { status: 502 },
    );
  }
}
