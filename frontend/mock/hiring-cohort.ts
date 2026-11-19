import { categoryKeywords, skillCategories } from "@/lib/skill-categories";

export interface DemoCandidate {
  id: string;
  name: string;
  synthetic: true;
  outcome: "passed" | "applied";
  keywordLevels: Record<string, number>;
  certificates: string[];
  gpa: number;
  career: string;
}

function sample(key: string) {
  let value = 2166136261;
  for (const char of key)
    value = Math.imul(value ^ char.charCodeAt(0), 16777619);
  value = Math.imul(value ^ (value >>> 16), 2246822507);
  return ((value ^ (value >>> 13)) >>> 0) / 4294967296;
}

export function demoCandidate(
  index: number,
  keywords: readonly string[],
): DemoCandidate {
  const id = `demo-candidate-${String(index + 1).padStart(3, "0")}`;
  const passed = index < 50;
  const specialty = index % skillCategories.length;
  const keywordLevels = Object.fromEntries(
    keywords.map((keyword) => {
      const category = skillCategories.findIndex((group) =>
        group.keywords.some((key) => key === keyword),
      );
      const strength =
        category === specialty ? 17 : category === (specialty + 1) % 10 ? 9 : 0;
      const value =
        18 + sample(`${id}:${keyword}`) * 45 + (passed ? 13 : 0) + strength;
      return [keyword, Math.min(98, Math.round(value))];
    }),
  );
  return {
    id,
    name: `가상 지원자 ${String(index + 1).padStart(3, "0")}`,
    synthetic: true,
    outcome: passed ? "passed" : "applied",
    keywordLevels,
    certificates: ["정보처리기사", "SQLD", "AWS SAA"].slice(0, index % 4),
    gpa: Math.round((2.8 + sample(`${id}:gpa`) * 1.5) * 10) / 10,
    career: index % 3 === 0 ? "신입" : `경력 ${1 + (index % 6)}년`,
  };
}

// Isolated UI fixtures: 150 applicants including exactly 50 successful profiles.
// IDs, scores and qualifications are fictional; no real accounts/DB rows are created.
export function createHiringCohort(
  jobId: string,
  keywords: readonly string[] = categoryKeywords,
) {
  const people = Array.from({ length: 150 }, (_, index) =>
    demoCandidate(index, keywords),
  );
  return {
    source: "SYNTHETIC" as const,
    version: "hiring-preview-20261119",
    jobId,
    people,
    passed: people.filter((person) => person.outcome === "passed"),
  };
}

export function meanKeywordLevels(
  people: DemoCandidate[],
  keywords: readonly string[],
) {
  return Object.fromEntries(
    keywords.map((keyword) => [
      keyword,
      people.length
        ? Math.round(
            people.reduce(
              (sum, person) => sum + (person.keywordLevels[keyword] ?? 0),
              0,
            ) / people.length,
          )
        : 0,
    ]),
  );
}

export function demoMyProfile() {
  return {
    ...demoCandidate(174, categoryKeywords),
    id: "demo-me",
    name: "내 프로필 예시",
    certificates: ["정보처리기사", "SQLD"],
    gpa: 3.8,
    career: "신입",
  };
}
