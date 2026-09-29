"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { GrowthState } from "@/types/growth";
import type { JobAnalysis } from "@/types/workspace";
import { levelNames } from "@/lib/growth/catalog";
export function JobLevelComparison({ job }: { job: JobAnalysis }) {
  const [g, setG] = useState<GrowthState | null>(null);
  useEffect(() => {
    let active = true;
    fetch("/api/growth")
      .then((r) => r.json())
      .then((d) => {
        if (active) setG(d.growth || null);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return (
    <section className="career-panel growth-hub">
      <h2>공고와 내 준비 상태</h2>
      <p>
        공고에 수준 기준이 없으면 충족·부족으로 단정하지 않아요. 원문의 실제
        요구 내용을 확인해 주세요.
      </p>
      <div className="growth-cards">
        {[...new Set([...job.required, ...job.preferred, ...job.unknown])].map(
          (skill) => {
            const r = g?.reviews.find(
              (r) => r.skill === skill && r.status !== "excluded",
            );
            return (
              <article className="growth-skill" key={skill}>
                <h3>
                  {skill} ·{" "}
                  {job.required.includes(skill)
                    ? "필수"
                    : job.preferred.includes(skill)
                      ? "우대"
                      : "분류 미확인"}
                </h3>
                <p>공고 요구 수준: 미명시</p>
                <p>
                  내 확인 수준:{" "}
                  {r?.level
                    ? `LV${r.level} · ${levelNames[r.level]}`
                    : "확인할 자료가 부족해요"}
                </p>
                <Link href="/my-skills?tab=skills">내 근거·다음 과제 확인 →</Link>
              </article>
            );
          },
        )}
      </div>
      <details>
        <summary>공고의 실제 요구 내용 확인</summary>
        <pre>{job.text}</pre>
      </details>
    </section>
  );
}
