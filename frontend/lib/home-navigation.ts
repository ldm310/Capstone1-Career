export const homeFeatures = [
  {
    id: "jobs",
    title: "채용공고",
    detail: "검색, 저장, 역량 비교",
    action: "공고 보기",
    href: "/jobs",
  },
  {
    id: "analysis",
    title: "분석",
    detail: "GitHub, 이력서로 공고 비교 준비",
    action: "분석 시작",
    href: "/analysis",
  },
] as const;
export type HomeFeatureId = (typeof homeFeatures)[number]["id"];
