import type { Finding } from "@/types/workspace";
import {
  emptyGrowth,
  type GrowthState,
  type SkillReview,
} from "@/types/growth";
import { canonical } from "./catalog";
export function mergeReviews(
  growth: GrowthState = emptyGrowth,
  findings: Finding[],
) {
  const reviews = structuredClone(growth.reviews);
  for (const f of findings) {
    const skill = canonical(f.skill);
    if (!reviews.some((r) => r.evidenceIds.includes(f.id))) {
      const old = reviews.find((r) => r.skill === skill);
      if (old) {
        old.evidenceIds = [...old.evidenceIds, f.id];
      } else
        reviews.push({
          skill,
          original: f.skill,
          level: null,
          status: "pending",
          reason:
            "자료에서 기술 관련 내용을 찾았어요. 언급만으로 수준을 확정하지 않아요.",
          evidenceIds: [f.id],
        } satisfies SkillReview);
    }
  }
  return { ...growth, reviews };
}
