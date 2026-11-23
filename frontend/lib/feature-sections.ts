export const featureSections = {
  experience: {
    path: "/experience",
    title: "역량 체험",
    description: "채용공고 예시의 역량 분석",
    tabs: [["example", "공고 예시"]],
  },
  notices: {
    path: "/notices",
    title: "공지사항",
    description: "서비스 소식과 이용 안내",
    tabs: [["list", "전체 공지"]],
  },
  analysis: {
    path: "/analysis",
    title: "분석",
    description: "GitHub, 이력서 등록 및 공고별 역량 비교",
    tabs: [["sources", "분석 자료"]],
  },
  jobs: {
    path: "/jobs",
    title: "채용공고",
    description: "채용공고 검색 및 자격요건, 역량 비교",
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
    description: "저장한 공고와 회원 정보 관리",
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
    // 이전 역량, 과제 경로는 공고별 비교 흐름으로 보낸다.
    tasks: "/jobs",
    plan: "/jobs",
    interview: "/jobs",
    jobs: "/jobs",
    saved: "/my-page",
    profile: "/my-page?tab=profile",
  };
  return routes[tab || ""] || "/analysis";
}
