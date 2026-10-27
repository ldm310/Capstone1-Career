export const featureSections = {
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
    sources: "/my-data",
    share: "/my-data?tab=share",
    skills: "/my-skills",
    // 진행 중 과제, 주간 계획, 면접 준비는 없앴으므로 추천 과제로 보낸다.
    tasks: "/my-skills?tab=next",
    plan: "/my-skills?tab=next",
    interview: "/my-skills?tab=next",
    jobs: "/jobs",
    saved: "/my-page",
    profile: "/my-page?tab=profile",
  };
  return routes[tab || ""] || "/my-skills";
}
