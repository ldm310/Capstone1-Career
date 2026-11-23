import examples from "./reviewed-keyword-examples.json";
import { studyDemoJobs } from "@/lib/study-prototype";
import type { SavedPostingLevel } from "@/types/posting-level";
import type { PublicJob } from "@/types/public-job";

// One public, deterministic preview. These values match the local demo fixture,
// not the current viewer's account or a real applicant cohort.
const scores: Record<string, [number, number]> = {
  L: [34, 91],
  B: [26, 88],
  D: [94, 88],
  O: [63, 50],
  Q: [26, 76],
  F: [52, 55],
};
export const experienceLevels: SavedPostingLevel[] = examples.examples.map(
  (keyword) => ({
    keywordId: keyword.id,
    text: keyword.text,
    categoryCodes: keyword.categoryCodes,
    score: scores[keyword.categoryCodes[0]][0],
    referenceScore: scores[keyword.categoryCodes[0]][1],
    referenceKind: "SYNTHETIC_APPLICANTS",
    evaluationKind: "DEMO",
    evaluatedAt: "2026-11-23T00:00:00+09:00",
  }),
);
export const experienceJob: PublicJob = {
  ...studyDemoJobs[0],
  experience: ["experienced"],
  closesAt: null,
  postedAt: null,
  posting: [
    { title: "주요 업무", items: ["웹 서비스 API 개발과 유지보수"] },
    {
      title: "자격요건",
      items: examples.examples
        .filter((item) =>
          item.categoryCodes.some((code) => ["B", "D", "L"].includes(code)),
        )
        .map((item) => item.text),
    },
    {
      title: "우대사항",
      items: examples.examples
        .filter((item) =>
          item.categoryCodes.some((code) => ["O", "Q", "F"].includes(code)),
        )
        .map((item) => item.text),
    },
  ],
};
