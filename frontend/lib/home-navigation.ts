export const homeFeatures = [
  {
    id: "jobs",
    title: "채용공고",
    detail: "검색, 저장, 역량 비교",
    action: "공고 보기",
    href: "/jobs",
  },
  {
    id: "skills",
    title: "내 역량",
    detail: "분석 결과, 과제, 면접 준비",
    action: "역량 보기",
    href: "/my-skills",
  },
  {
    id: "data",
    title: "내 자료",
    detail: "자료 추가, 포트폴리오 공유",
    action: "자료 추가",
    href: "/my-data",
  },
] as const;
export type HomeFeatureId = (typeof homeFeatures)[number]["id"];
