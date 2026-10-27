// 더미 데이터: 실제 지원자, 합격자 통계가 연결되기 전까지 공고별 비교 화면을 보여주기 위한 예시 값이다.
export const benchmarkAxes = [
  "프로젝트 수",
  "기술 스택 일치",
  "프로젝트 규모",
  "협업, 역할",
  "배포, 운영",
  "성과 지표",
  "코드 품질",
  "문서화",
  "포트폴리오 완성도",
  "오픈소스, 외부 활동",
] as const;

export interface BenchmarkRow {
  axis: (typeof benchmarkAxes)[number];
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

// 같은 공고는 항상 같은 값을 보여주도록 공고 ID로 시드를 고정한다. 점수는 0~100.
export function applicantBenchmark(jobId: string): ApplicantBenchmark {
  const rand = seeded(jobId);
  const between = (min: number, max: number) =>
    Math.round(min + rand() * (max - min));
  const rows = benchmarkAxes.map((axis) => {
    const applicants = between(35, 60);
    const passed = Math.min(98, applicants + between(12, 32));
    const me = between(15, 95);
    return { axis, me, applicants, passed };
  });
  const applicantCount = between(80, 420);
  return {
    rows,
    applicantCount,
    passedCount: Math.max(
      3,
      Math.round(applicantCount * (0.03 + rand() * 0.05)),
    ),
  };
}
