export const featureSections = {
  analysis: {
    path: "/analysis",
    title: "분석",
    description: "내 경험을 담고, 관심 있는 공고에서 비교해요.",
    tabs: [["sources", "분석 자료"]],
  },
  jobs: {
    path: "/jobs",
    title: "채용공고",
    description: "공고를 찾고 내 역량과 비교해요.",
    tabs: [["browse", "전체 공고"]],
  },
  skills: {
    path: "/my-skills",
    title: "내 역량",
    description: "찾은 기술을 확인하고 다음 과제를 골라요.",
    tabs: [
      ["skills", "분석 결과"],
      ["next", "추천 과제"],
    ],
  },
  data: {
    path: "/my-data",
    title: "내 자료",
    description: "자료를 추가하고 포트폴리오를 공유해요.",
    tabs: [
      ["sources", "자료 추가"],
      ["share", "포트폴리오 공유"],
    ],
  },
  mypage: {
    path: "/my-page",
    title: "마이페이지",
    description: "저장한 공고와 내 정보를 관리해요.",
    tabs: [
      ["saved", "저장한 공고"],
      ["profile", "내 정보"],
    ],
  },
} as const;
export type FeatureSection = keyof typeof featureSections;
export function selectedSectionTab(
  section: FeatureSection,
  tab: string | null,
) {
  const options = featureSections[section].tabs;
  return options.some(([key]) => key === tab) ? tab! : options[0][0];
}
export function legacyDestination(tab: string | null) {
  const routes: Record<string, string> = {
    sources: "/analysis",
    share: "/my-data?tab=share",
    skills: "/jobs",
    // 이전 역량·과제 경로는 공고별 비교 흐름으로 보낸다.
    tasks: "/jobs",
    plan: "/jobs",
    interview: "/jobs",
    jobs: "/jobs",
    saved: "/my-page",
    profile: "/my-page?tab=profile",
  };
  return routes[tab || ""] || "/analysis";
}
