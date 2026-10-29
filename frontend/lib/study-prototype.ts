import type { PostingSection, PublicJob } from "@/types/public-job";

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
  level?: 1 | 2 | 3;
};
export type JobComparison = {
  required: Requirement[];
  preferred: Requirement[];
};

// Hand-authored UI scenarios. These are not a scoring model or employer data.
export const studyDemoJobs: PublicJob[] = [
  {
    id: "study-demo-backend",
    company: "커리어랩 · 가상 기업",
    title: "백엔드 서비스 개발자",
    category: "backend",
    location: "서울",
    employment: "정규직",
    experience: ["entry", "any"],
    workplace: "하이브리드 근무",
    postedAt: "2026-10-03T00:00:00+09:00",
    closesAt: "2026-10-20T18:00:00+09:00",
    url: "",
    dummy: true,
    skills: ["SQL", "REST API", "Docker"],
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
    dummy: true,
    skills: ["Python", "SQL", "Airflow"],
  },
  {
    id: "study-demo-backend-intern",
    company: "서버스튜디오 · 가상 기업",
    title: "백엔드 개발자 인턴",
    category: "backend",
    location: "서울",
    employment: "인턴",
    experience: ["intern"],
    workplace: "원격 근무",
    postedAt: "2026-10-01T00:00:00+09:00",
    closesAt: "2026-10-25T18:00:00+09:00",
    url: "",
    dummy: true,
    skills: ["Java", "Spring Boot", "PostgreSQL"],
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
export function qualificationLabel(comparison: JobComparison) {
  return comparison.required.every((r) => r.satisfied) ? "만족" : "불만족";
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
// 예시 공고 본문: exampleComparison과 같은 조건을 공고 형식으로 보여준다.
export function examplePosting(job: PublicJob): PostingSection[] {
  const [first = "", second = "", third = ""] = job.skills ?? [];
  return [
    {
      title: "주요 업무",
      items:
        job.category === "data"
          ? ["데이터 수집, 적재 파이프라인 개발", "배치 작업 운영과 품질 관리"]
          : ["서비스 API 개발과 운영", "데이터베이스 설계와 성능 개선"],
    },
    {
      title: "자격요건",
      items: [
        `${first} 활용 경험`,
        `${second} 프로젝트 경험`,
        job.category === "data"
          ? "실무 경력 2년 이상"
          : "프로젝트 결과 설명 가능",
      ],
    },
    {
      title: "우대사항",
      items: [
        `${first} 테스트 작성`,
        `${second} 개선 경험`,
        `${third} 활용 경험`,
        "기술 문서 작성 경험",
        "오픈소스 기여 경험",
      ],
    },
    {
      title: "근무 조건",
      items: [
        `${job.location}, ${job.workplace ?? "근무 방식 협의"}`,
        job.employment,
      ],
    },
  ];
}
