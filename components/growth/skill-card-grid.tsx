"use client";
import { useEffect, useState } from "react";
import {
  ChevronRight,
  Code2,
  Database,
  Server,
  BarChart3,
  Sparkles,
  Boxes,
} from "lucide-react";
import type { Finding } from "@/types/workspace";
import type { SkillReview } from "@/types/growth";
import {
  categoryOrder,
  scoreTier,
  scoreTiers as tierList,
  skillCategory,
  skillScore,
} from "@/lib/growth/score";

const icons: Record<string, typeof Code2> = {
  Backend: Code2,
  Database,
  DevOps: Server,
  Data: BarChart3,
  AI: Sparkles,
  기타: Boxes,
};

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
    const review = reviews.find((r) => r.skill === skill);
    const evidence = findings.filter(
      (f) => review?.evidenceIds.includes(f.id) || f.skill === skill,
    );
    return { skill, review, evidence, score: skillScore(review, evidence) };
  });
}

// 기술을 분야별 카드로 모아 보여준다. 막대는 화면에 들어오면 점수만큼 차오른다.
export function SkillCardGrid({
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
  const groups = categoryOrder
    .map((name) => ({
      name,
      items: items
        .filter((i) => skillCategory(i.skill) === name)
        .sort((a, b) => b.score - a.score),
    }))
    .filter((g) => g.items.length);
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
      {groups.map((group) => {
        const Icon = icons[group.name] ?? Boxes;
        return (
          <section key={group.name} className="skill-group">
            <h3>
              {group.name}
              <small>{group.items.length}개 기술</small>
            </h3>
            <ul className="skill-cards">
              {group.items.map(({ skill, score, review, evidence }) => {
                const tier = scoreTier(score);
                const next = [...tierList].reverse().find((t) => t.min > score);
                const projects = new Set(evidence.map((f) => f.title)).size;
                const latest = evidence
                  .map((f) => f.detectedAt)
                  .sort()
                  .at(-1);
                return (
                  <li key={skill}>
                    <button
                      type="button"
                      className={`plain-button skill-card tier-${scoreTiers(score)}${evidence.length ? "" : " is-empty"}`}
                      onClick={() => onSelect(skill)}
                      aria-label={`${skill} LV ${score} ${tier.name} 자세히`}
                    >
                      <span className="skill-card-head">
                        <span className="skill-card-icon" aria-hidden="true">
                          <Icon size={18} />
                        </span>
                        <strong className="skill-card-name">{skill}</strong>
                        {review?.status === "pending" && (
                          <span className="skill-card-flag">확인 전</span>
                        )}
                        <ChevronRight
                          size={18}
                          className="skill-card-chevron"
                          aria-hidden="true"
                        />
                      </span>
                      <span className="skill-card-score">
                        <span className="skill-card-number">
                          <small>LV</small>
                          <CountUp value={score} run={filled} />
                        </span>
                        <span className="skill-card-tier">{tier.name}</span>
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
                        {[20, 40, 60, 80].map((t) => (
                          <i key={t} style={{ left: `${t}%` }} />
                        ))}
                      </span>
                      {next && (
                        <span className="skill-card-next">
                          {next.name}까지 <b>{next.min - score}</b>
                        </span>
                      )}
                      <span className="skill-card-meta">
                        {evidence.length ? (
                          <>
                            <span>
                              프로젝트 <b>{projects}</b>, 근거{" "}
                              <b>{evidence.length}</b>
                            </span>
                            {latest && (
                              <span>
                                {new Date(latest).toLocaleDateString("ko-KR", {
                                  month: "numeric",
                                  day: "numeric",
                                })}{" "}
                                확인
                              </span>
                            )}
                          </>
                        ) : (
                          <span>아직 근거가 없어요</span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

// 점수 구간별 색 단계(1~5). 막대 색을 구간마다 조금씩 진하게 바꾼다.
function scoreTiers(score: number) {
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
