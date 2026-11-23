import type { Finding } from "@/types/workspace";
import type { SkillReview } from "@/types/growth";

export interface PostingKeyword {
  id: string;
  text: string;
  categoryCodes: string[];
  level: number | null;
}
export interface PersonalKeyword extends PostingKeyword {
  myLevel: number | null;
  evidence: Finding[];
  assessed: boolean;
}
const normalized = (value: string) =>
  value
    .normalize("NFC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();

// Existing technology scores must never be copied onto a different requirement.
// Name overlap produces a review candidate, not proof of proficiency or an LV.
export function connectJobEvidence(
  keywords: PostingKeyword[],
  findings: Finding[],
  reviews: SkillReview[],
): PersonalKeyword[] {
  return keywords.map((keyword) => {
    const review = reviews.find(
      (item) =>
        ["confirmed", "edited"].includes(item.status) &&
        (item.skill === keyword.id ||
          normalized(item.skill) === normalized(keyword.text)),
    );
    const reviewedEvidence = findings.filter((item) =>
      review?.evidenceIds.includes(item.id),
    );
    const score = review?.score;
    const assessed =
      !!review &&
      reviewedEvidence.length > 0 &&
      typeof score === "number" &&
      Number.isFinite(score) &&
      score >= 0 &&
      score <= 100;
    const text = ` ${normalized(keyword.text)} `;
    const candidates = findings.filter((finding) => {
      const skill = normalized(finding.skill);
      return (
        normalized(finding.skill) === normalized(keyword.text) ||
        (skill.length >= 2 && text.includes(` ${skill} `)) ||
        normalized(finding.quote).includes(normalized(keyword.text))
      );
    });
    return {
      ...keyword,
      myLevel: assessed ? score! : null,
      assessed,
      evidence: [
        ...new Map(
          [...reviewedEvidence, ...candidates].map((item) => [item.id, item]),
        ).values(),
      ],
    };
  });
}
