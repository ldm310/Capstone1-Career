import { targetSkills } from "@/lib/workspace-selectors";
import { patterns } from "@/lib/skill-patterns";
import type { PostingSection } from "@/types/public-job";

// 더미 데이터: 실제 지원자, 합격자 통계가 연결되기 전까지 공고별 비교 화면을 보여주기 위한 예시 값이다.
// 축은 공고의 기술이고 값은 내 역량과 같은 LV(1~100)다.

export interface BenchmarkRow {
  axis: string;
  me: number;
  applicants: number;
  passed: number;
}
export interface ApplicantBenchmark {
  rows: BenchmarkRow[];
  applicantCount: number;
  passedCount: number;
}

function seeded(text: string) {
  let h = 2166136261;
  for (const c of text) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}

// 공고 기술을 먼저 쓰고, 레이더가 모양을 갖추도록 직무 기본 기술로 5개 이상을 채운다. 최대 8개.
export function benchmarkSkills(job: { skills?: string[]; category: string }) {
  const own = [...new Set(job.skills ?? [])];
  const fill = (targetSkills[job.category] ?? targetSkills.data).filter(
    (s) => !own.includes(s),
  );
  return [...own, ...fill.slice(0, Math.max(0, 5 - own.length))].slice(0, 8);
}

// 같은 공고는 항상 같은 값을 보여주도록 공고 ID로 시드를 고정한다.
// myLevels에 있는 기술은 내 실제 LV를 쓰고, 없으면 예시 값을 쓴다.
export function applicantBenchmark(
  jobId: string,
  skills: string[],
  myLevels?: Record<string, number>,
): ApplicantBenchmark {
  const rand = seeded(jobId);
  const between = (min: number, max: number) =>
    Math.round(min + rand() * (max - min));
  const rows = skills.map((axis) => {
    const applicants = between(22, 48);
    const passed = Math.min(95, applicants + between(14, 32));
    const sample = between(8, 88);
    return { axis, me: myLevels?.[axis] ?? sample, applicants, passed };
  });
  // 우대사항 비율이 의미 있게 보이도록 합격자를 20명 이상으로 둔다.
  const applicantCount = between(240, 620);
  return {
    rows,
    applicantCount,
    passedCount: Math.round(applicantCount * (0.08 + rand() * 0.06)),
  };
}

export interface PreferredRow {
  text: string;
  count: number;
  rate: number;
  // 항목에 기술 이름이 있으면 그 기술의 합격자 평균 LV와 내 LV를 함께 보여준다.
  skill?: string;
}

// 우대사항 목록: 모든 공고에 공통 두 항목을 두고, 공고 본문의 우대사항을 잇는다.
// 본문이 없으면 공고 기술로 만든다.
export function preferredItems(
  job: { skills?: string[] },
  posting?: PostingSection[],
) {
  const fromPosting =
    posting?.find((s) => /우대/.test(s.title))?.items ??
    (job.skills ?? []).slice(0, 3).map((s) => `${s} 활용 경험`);
  return [
    "컴퓨터공학, 소프트웨어공학 등 관련 전공",
    "개발 관련 프로젝트 또는 실무 경험",
    ...fromPosting,
  ];
}

export function itemSkill(text: string, skills: string[]) {
  return skills.find((s) =>
    patterns[s] ? patterns[s].test(text) : text.includes(s),
  );
}

// 합격자 중 각 우대사항을 충족한 사람 수. 공고 ID로 시드를 고정한 예시 값이다.
export function passedPreferred(
  jobId: string,
  items: string[],
  passedCount: number,
  skills: string[],
): PreferredRow[] {
  const rand = seeded(`${jobId}:preferred`);
  return items.map((text, i) => {
    // 공통 항목은 대부분 충족하고, 본문 항목은 30~80% 사이로 흩어 둔다.
    const rate = i < 2 ? 0.7 + rand() * 0.25 : 0.3 + rand() * 0.5;
    const count = Math.max(1, Math.round(passedCount * rate));
    return {
      text,
      count,
      rate: Math.round((count / passedCount) * 100),
      skill: itemSkill(text, skills),
    };
  });
}
