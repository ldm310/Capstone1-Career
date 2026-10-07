import type { PublicJob } from "@/types/public-job";

export type StudyTier = "low" | "middle" | "high";
export const tierLabels: Record<StudyTier, string> = {
  low: "Low",
  middle: "Middle",
  high: "High",
};
export function studyTier(value: string | null): StudyTier | null {
  return value === "low" || value === "middle" || value === "high"
    ? value
    : null;
}
export type Requirement = {
  text: string;
  skill?: string;
  satisfied: boolean;
  evidence: string;
  level?: 1 | 2 | 3;
};
export type JobComparison = {
  required: Requirement[];
  preferred: Requirement[];
};

// Hand-authored UI scenarios. These are not a scoring model or employer data.
export const studyDemoJobs: PublicJob[] = [
  {
    id: "study-demo-rag",
    company: "커리어랩 · 가상 기업",
    title: "AI 서비스 개발자",
    category: "ax",
    location: "서울",
    employment: "정규직",
    experience: ["entry", "any"],
    workplace: "하이브리드 근무",
    postedAt: "2026-10-03T00:00:00+09:00",
    closesAt: "2026-10-20T18:00:00+09:00",
    url: "",
    skills: ["Python", "RAG", "Docker"],
  },
  {
    id: "study-demo-data",
    company: "데이터노트 · 가상 기업",
    title: "데이터 파이프라인 엔지니어",
    category: "data",
    location: "경기 판교",
    employment: "정규직",
    experience: ["experienced"],
    workplace: "사무실 근무",
    postedAt: "2026-10-02T00:00:00+09:00",
    closesAt: "2026-10-15T18:00:00+09:00",
    url: "",
    skills: ["Python", "SQL", "Airflow"],
  },
  {
    id: "study-demo-ml",
    company: "모델스튜디오 · 가상 기업",
    title: "머신러닝 엔지니어 인턴",
    category: "ml",
    location: "서울",
    employment: "인턴",
    experience: ["intern"],
    workplace: "원격 근무",
    postedAt: "2026-10-01T00:00:00+09:00",
    closesAt: "2026-10-25T18:00:00+09:00",
    url: "",
    skills: ["Python", "PyTorch", "MLflow"],
  },
];
export function exampleComparison(
  job: PublicJob,
  tier: StudyTier,
): JobComparison {
  const skills = job.skills ?? [];
  // Different skill levels can coexist in one relative-tier scenario.
  // These explicit fixtures must never become a tier-to-LV scoring rule.
  const exampleLevels: Record<StudyTier, readonly (1 | 2 | 3)[]> = {
    low: [2, 1, 1],
    middle: [2, 2, 1],
    high: [3, 2, 2],
  };
  const requirement = (
    text: string,
    skill: string | undefined,
    satisfied: boolean,
  ): Requirement => ({
    text,
    skill,
    satisfied,
    ...(satisfied && skill
      ? { level: exampleLevels[tier][skills.indexOf(skill)] ?? 1 }
      : {}),
    evidence: satisfied
      ? "예시 프로젝트 자료에서 해당 경험을 확인했어요."
      : "체험 시나리오에서 해당 조건을 충족하지 않는 것으로 설정했어요.",
  });
  return {
    required: [
      requirement(`${skills[0]} 활용 경험`, skills[0], true),
      requirement(`${skills[1]} 프로젝트 경험`, skills[1], true),
      requirement(
        job.category === "data"
          ? "실무 경력 2년 이상"
          : "프로젝트 결과 설명 가능",
        undefined,
        job.category !== "data",
      ),
    ],
    preferred: [
      requirement(`${skills[0]} 테스트 작성`, skills[0], true),
      requirement(`${skills[1]} 개선 경험`, skills[1], tier !== "low"),
      requirement(`${skills[2]} 활용 경험`, skills[2], tier !== "low"),
      requirement("기술 문서 작성 경험", undefined, true),
      requirement("오픈소스 기여 경험", undefined, tier === "high"),
    ],
  };
}
export function qualificationLabel(comparison?: JobComparison) {
  return !comparison
    ? "판정 대기"
    : comparison.required.every((r) => r.satisfied)
      ? "만족"
      : "불만족";
}
export function matchingSkills(comparison: JobComparison) {
  return [
    ...new Map(
      comparison.preferred
        .filter((r) => r.satisfied && r.skill && r.level)
        .map((r) => [r.skill!, { skill: r.skill!, level: r.level! }]),
    ).values(),
  ];
}
export type StudyOffer = {
  id: string;
  jobId: string;
  tier: StudyTier;
  title: string;
  description: string;
  roadmap: { title: string; outcome: string }[];
};
export function studyOffers(job: PublicJob, tier: StudyTier): StudyOffer[] {
  const [first = "기초 기술", second = "프로젝트 기술", third = "실행 환경"] =
    job.skills ?? [];
  const topics =
    tier === "low"
      ? [
          {
            title: `${first} 기본 기능 실행`,
            outcome: "작은 예제를 실행하고 입력과 결과를 기록해요.",
          },
          {
            title: `${second} 기능 연결`,
            outcome: "기존 프로젝트에 기능을 연결하고 실행 방법을 정리해요.",
          },
          {
            title: "프로젝트 적용 결과 공유",
            outcome: "정상·실패 사례를 테스트하고 서로의 결과를 확인해요.",
          },
        ]
      : tier === "middle"
        ? [
            {
              title: `${second} 현재 결과 측정`,
              outcome: "평가할 사례와 측정 조건을 함께 정해요.",
            },
            {
              title: "문제 원인 확인·개선",
              outcome: "발견한 문제를 수정하고 같은 조건에서 전후를 비교해요.",
            },
            {
              title: `${third} 실행·재현 점검`,
              outcome: "실행 환경과 결과의 한계를 문서로 남겨요.",
            },
          ]
        : [
            {
              title: `${second} 심화 목표 정하기`,
              outcome: "공고와 내 프로젝트를 바탕으로 개선할 문제를 선택해요.",
            },
            {
              title: "대안 비교 실험",
              outcome: "여러 접근법의 품질·속도·비용을 비교해요.",
            },
            {
              title: "설계 검토·결과 공유",
              outcome: "선택 이유와 한계를 설명하고 재현 자료를 공유해요.",
            },
          ];
  return [
    {
      id: `${job.id}:${tier}:project`,
      jobId: job.id,
      tier,
      title: `${second} 프로젝트 함께 준비하기`,
      description: `${first}·${second} 중심으로 공고에 필요한 경험을 준비해요.`,
      roadmap: topics,
    },
    {
      id: `${job.id}:${tier}:evidence`,
      jobId: job.id,
      tier,
      title: `${first} 구현과 검증 스터디`,
      description: "작은 작업부터 시작해 실행 결과와 설명을 함께 정리해요.",
      roadmap: [
        {
          title: `${first} 프로젝트 점검`,
          outcome: "보유한 구현과 추가로 확인할 결과를 구분해요.",
        },
        ...topics.slice(1),
      ],
    },
  ];
}
