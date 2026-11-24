import type { Finding } from "@/types/workspace";
import type { SkillReview } from "@/types/growth";

// 기술 점수(1~100). 저장된 score가 있으면 쓰고, 없으면 확인된 단계와 근거 양으로 계산한다.
// 단계별 과제(1~3단계)와는 별개로, 카드에서 성장 정도를 보여주기 위한 값이다.
const stageBase = { 0: 6, 1: 22, 2: 46, 3: 70 } as const;
export function skillScore(
  review: SkillReview | undefined,
  evidence: Finding[],
) {
  if (review?.score) return Math.max(1, Math.min(100, review.score));
  const projects = new Set(evidence.map((f) => f.title)).size;
  const coded = evidence.filter((f) => f.type === "implementation").length;
  const bonus = Math.min(
    24,
    coded * 6 + (evidence.length - coded) * 3 + projects * 2,
  );
  return Math.max(1, Math.min(100, stageBase[review?.level ?? 0] + bonus));
}

export const scoreTiers = [
  { min: 80, name: "심화 개선" },
  { min: 60, name: "통합 구현" },
  { min: 40, name: "기능 구현" },
  { min: 20, name: "기초 적용" },
  { min: 1, name: "입문" },
] as const;
export function scoreTier(score: number) {
  return scoreTiers.find((t) => score >= t.min)!;
}
