export type Level = 1 | 2 | 3;
export interface SkillReview {
  skill: string;
  original: string;
  level: Level | null;
  status: "pending" | "confirmed" | "edited" | "excluded" | "appeal";
  reason: string;
  evidenceIds: string[];
  // 1~100 기술 점수. 없으면 단계와 근거로 계산한다.
  score?: number;
}
export interface GrowthTask {
  id: string;
  skill: string;
  level: Level;
  baseline: Level | null;
  baselineEvidence: string[];
  startedAt: string;
  date: string;
  status: "active" | "needs_evidence" | "completed";
  submissions: {
    at: string;
    evidence: string;
    explanation: string;
    feedback: string;
  }[];
}
export interface GrowthState {
  reviews: SkillReview[];
  tasks: GrowthTask[];
}
export const emptyGrowth: GrowthState = {
  reviews: [],
  tasks: [],
};
