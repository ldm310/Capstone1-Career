import { emptyGrowth, type GrowthState } from "@/types/growth";
export const sample: GrowthState = {
  ...emptyGrowth,
  nickname: "나",
  reviews: [
    {
      skill: "Docker",
      original: "Docker",
      level: 1,
      status: "confirmed",
      reason: "샘플 프로젝트의 빌드·실행 기록에서 기초 기준을 확인한 예시예요.",
      evidenceIds: [],
    },
    {
      skill: "Python",
      original: "Python",
      level: 2,
      status: "confirmed",
      reason: "샘플 프로젝트의 예외 처리·외부 데이터 연동 근거 예시예요.",
      evidenceIds: [],
    },
    {
      skill: "PostgreSQL",
      original: "postgres",
      level: null,
      status: "pending",
      reason: "기술 언급은 있지만 실행 결과가 부족해요.",
      evidenceIds: [],
    },
  ],
};
