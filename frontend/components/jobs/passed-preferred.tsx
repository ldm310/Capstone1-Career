"use client";
import {
  applicantBenchmark,
  benchmarkSkills,
  passedPreferred,
  preferredItems,
} from "@/lib/applicant-benchmark";
import { patterns } from "@/lib/skill-patterns";
import { useMyLevels } from "@/lib/my-levels";
import type { PostingSection, PublicJob } from "@/types/public-job";

// 합격자가 공고의 우대사항을 얼마나 충족했는지 보여준다. 기술 항목은 합격자 평균 LV와 내 LV를 붙인다.
export function PassedPreferred({
  job,
  posting,
}: {
  job: PublicJob;
  posting?: PostingSection[];
}) {
  const radarSkills = benchmarkSkills(job);
  const matchable = [
    ...new Set([
      ...radarSkills,
      ...(job.skills ?? []),
      ...Object.keys(patterns),
    ]),
  ];
  const { rows: levels, passedCount } = applicantBenchmark(job.id, radarSkills);
  const rows = passedPreferred(
    job.id,
    preferredItems(job, posting ?? job.posting),
    passedCount,
    matchable,
  );
  const mine = useMyLevels([
    ...new Set(rows.flatMap((r) => (r.skill ? [r.skill] : []))),
  ]);
  return (
    <section className="study-requirements passed-preferred">
      <h3>합격자의 우대사항 충족 현황</h3>
      <p className="study-muted">
        예시 데이터, 전체 합격자 {passedCount}명 기준, 항목별 중복 집계
      </p>
      <ul>
        {rows.map((r) => {
          const passed = levels.find((l) => l.axis === r.skill)?.passed;
          const me = r.skill ? mine?.[r.skill] : undefined;
          return (
            <li key={r.text}>
              <div className="passed-preferred-head">
                <span>{r.text}</span>
                <b>
                  {r.count} / {passedCount}명, {r.rate}%
                </b>
              </div>
              <span
                className="passed-preferred-bar"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={r.rate}
                aria-label={`${r.text} 충족 비율`}
              >
                <span style={{ width: `${r.rate}%` }} />
              </span>
              {r.skill && (
                <small
                  className={
                    passed !== undefined && me !== undefined && me < passed
                      ? "is-behind"
                      : ""
                  }
                >
                  {[
                    r.skill,
                    passed !== undefined && `합격자 평균 LV ${passed},`,
                    me !== undefined ? `나 LV ${me}` : "내 자료 없음",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                </small>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
