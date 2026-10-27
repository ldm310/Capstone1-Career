"use client";
import { useEffect, useState } from "react";
import type { Finding } from "@/types/workspace";
import type { SkillReview } from "@/types/growth";
import { scoreTier, skillScore } from "@/lib/growth/score";

export interface SkillCardItem {
  skill: string;
  score: number;
  review?: SkillReview;
  evidence: Finding[];
}

export function skillCardItems(
  names: string[],
  reviews: SkillReview[],
  findings: Finding[],
): SkillCardItem[] {
  return names.map((skill) => {
    // 이름 수정으로 같은 기술이 둘 이상이면 단계가 높은 것을 쓰고 근거는 합친다.
    const same = reviews.filter((r) => r.skill === skill);
    const review = [...same].sort((a, b) => (b.level ?? 0) - (a.level ?? 0))[0];
    const ids = new Set(same.flatMap((r) => r.evidenceIds));
    const evidence = findings.filter((f) => ids.has(f.id) || f.skill === skill);
    return { skill, review, evidence, score: skillScore(review, evidence) };
  });
}

// 모든 기술을 한 목록에 점수순으로 보여준다. 한 줄에 기술명, 레벨, 막대를 둔다.
export function SkillList({
  items,
  onSelect,
}: {
  items: SkillCardItem[];
  onSelect: (skill: string) => void;
}) {
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const sorted = [...items].sort(
    (a, b) => b.score - a.score || a.skill.localeCompare(b.skill),
  );
  const withEvidence = items.filter((i) => i.evidence.length);
  const average = withEvidence.length
    ? Math.round(
        withEvidence.reduce((sum, i) => sum + i.score, 0) / withEvidence.length,
      )
    : 0;
  return (
    <div className="skill-groups">
      <p className="skill-summary">
        근거 있는 기술 <b>{withEvidence.length}개</b>, 평균 <b>LV {average}</b>
      </p>
      <ul className="skill-rows">
        {sorted.map(({ skill, score, review, evidence }) => {
          const tier = scoreTier(score);
          return (
            <li key={skill}>
              <button
                type="button"
                className={`plain-button skill-row tier-${tierStep(score)}${evidence.length ? "" : " is-empty"}`}
                onClick={() => onSelect(skill)}
                aria-label={`${skill} LV ${score} ${tier.name} 자세히`}
                title={tier.name}
              >
                <span className="skill-row-name">
                  {skill}
                  {review?.status === "pending" && (
                    <small className="skill-card-flag">확인 전</small>
                  )}
                </span>
                <span className="skill-row-level">
                  <small>LV</small>
                  <CountUp value={score} run={filled} />
                </span>
                <span
                  className="skill-card-bar"
                  role="progressbar"
                  aria-valuemin={1}
                  aria-valuemax={100}
                  aria-valuenow={score}
                  aria-label={`${skill} 점수`}
                >
                  <span style={{ width: filled ? `${score}%` : "0%" }} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// 점수 구간별 색 단계(1~5). 막대 색을 구간마다 바꾼다.
function tierStep(score: number) {
  return score >= 80
    ? 5
    : score >= 60
      ? 4
      : score >= 40
        ? 3
        : score >= 20
          ? 2
          : 1;
}

// 점수를 0부터 목표값까지 짧게 올린다. 동작 줄이기 설정이면 바로 보여준다.
function CountUp({ value, run }: { value: number; run: boolean }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!run) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const id = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(id);
    }
    const start = performance.now(),
      duration = 900;
    let id = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setShown(Math.round(value * (1 - Math.pow(1 - t, 3))));
      if (t < 1) id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [value, run]);
  return <>{shown}</>;
}
