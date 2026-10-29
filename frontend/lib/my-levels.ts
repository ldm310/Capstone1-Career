"use client";
import { useEffect, useState } from "react";
import { openCareerSpace } from "@/lib/guest-session";
import { currentFindings } from "@/lib/workspace-selectors";
import { mergeReviews } from "@/lib/growth/model";
import { skillCardItems } from "@/components/growth/skill-card-grid";
import type { Finding } from "@/types/workspace";
import type { SkillReview } from "@/types/growth";

interface Source {
  findings: Finding[];
  reviews: SkillReview[];
}
// 공고 카드 여러 장이 같은 요청을 반복하지 않게 잠깐 공유한다.
let cached: { at: number; promise: Promise<Source | null> } | null = null;
function loadSource() {
  if (cached && Date.now() - cached.at < 30_000) return cached.promise;
  const promise = Promise.all([
    openCareerSpace().then((r) => (r.ok ? r.json() : null)),
    fetch("/api/growth").then((r) => (r.ok ? r.json() : null)),
  ])
    .then(([career, growth]) => {
      if (!career?.workspace || !growth?.growth) return null;
      const findings = currentFindings(career.workspace);
      if (!findings.length) return null;
      const reviews = mergeReviews(growth.growth, findings).reviews.filter(
        (r) => r.status !== "excluded",
      );
      return { findings, reviews };
    })
    .catch(() => null);
  cached = { at: Date.now(), promise };
  return promise;
}

// 기술별 내 LV(내 역량과 같은 계산). 자료가 하나도 없으면 null로 두어 예시 값을 쓰게 한다.
export function useMyLevels(skills: string[]) {
  const [levels, setLevels] = useState<Record<string, number> | null>(null);
  const key = skills.join("|");
  useEffect(() => {
    let active = true;
    void loadSource().then((source) => {
      if (!active || !source) return;
      setLevels(
        Object.fromEntries(
          skillCardItems(key.split("|"), source.reviews, source.findings).map(
            (c) => [c.skill, c.score],
          ),
        ),
      );
    });
    return () => {
      active = false;
    };
  }, [key]);
  return levels;
}
