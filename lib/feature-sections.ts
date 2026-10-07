export const featureSections = {
  studies: {
    path: "/studies",
    title: "내 스터디",
    description:
      "같은 공고를 준비하는 나의 스터디와 성장 기록을 한곳에서 확인하세요.",
    tabs: [["joined", "신청한 스터디"]],
  },
  jobs: {
    path: "/jobs",
    title: "채용공고",
    description: "관심 있는 기회를 찾고, 내 경험과 비교해 보세요.",
    tabs: [
      ["browse", "전체 공고"],
      ["saved", "저장한 공고"],
      ["jobs", "내 역량과 비교"],
    ],
  },
  skills: {
    path: "/my-skills",
    title: "내 역량 확인",
    description:
      "해온 일을 자료로 보여주세요. 찾은 기술과 근거를 함께 확인해요.",
    tabs: [
      ["sources", "자료 추가"],
      ["skills", "분석 결과·근거"],
      ["share", "포트폴리오 공유"],
    ],
  },
  preparation: {
    path: "/preparation",
    title: "취업 준비",
    description: "필요한 기술을 과제로 준비하고, 면접까지 이어가세요.",
    tabs: [
      ["skills", "다음 과제 찾기"],
      ["tasks", "진행 중인 과제"],
      ["plan", "주간 계획"],
      ["interview", "면접 준비"],
    ],
  },
  applications: {
    path: "/application-tracker",
    title: "지원 관리",
    description:
      "지원 기록과 제출 이력서, 다가오는 일정을 한곳에서 관리하세요.",
    tabs: [
      ["applications", "지원·이력서"],
      ["schedule", "일정·마감"],
    ],
  },
  growth: {
    path: "/growth",
    title: "성장 대시보드",
    description:
      "준비하며 쌓은 기록과 포인트를 확인하세요. 실력 점수가 아닌 성장 기록이에요.",
    tabs: [
      ["summary", "성장 현황"],
      ["history", "완료·포인트 내역"],
      ["ranking", "성장 랭킹"],
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
    sources: "/my-skills",
    skills: "/my-skills?tab=skills",
    share: "/my-skills?tab=share",
    tasks: "/preparation?tab=tasks",
    plan: "/preparation?tab=plan",
    interview: "/preparation?tab=interview",
    applications: "/application-tracker",
    schedule: "/application-tracker?tab=schedule",
    jobs: "/jobs?tab=jobs",
    ranking: "/growth?tab=ranking",
    history: "/growth?tab=history",
  };
  return routes[tab || ""] || "/growth";
}
