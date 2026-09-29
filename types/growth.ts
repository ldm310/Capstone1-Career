export type Level = 1 | 2 | 3;
export interface SkillReview {
  skill: string;
  original: string;
  level: Level | null;
  status: "pending" | "confirmed" | "edited" | "excluded" | "appeal";
  reason: string;
  evidenceIds: string[];
}
export interface GrowthTask {
  id: string;
  skill: string;
  level: Level;
  reward: number;
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
export interface Reward {
  id: string;
  taskId: string;
  skill: string;
  level: Level;
  points: number;
  at: string;
  reason: string;
}
export interface GrowthState {
  reviews: SkillReview[];
  tasks: GrowthTask[];
  rewards: Reward[];
  publicRanking: boolean;
  nickname: string;
}
export interface RankingRow {
  id: string;
  nickname: string;
  points: number;
  completed: number;
  rank: number;
}
export const emptyGrowth: GrowthState = {
  reviews: [],
  tasks: [],
  rewards: [],
  publicRanking: false,
  nickname: "",
};
