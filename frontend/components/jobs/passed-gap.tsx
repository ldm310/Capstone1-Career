"use client";
import { applicantBenchmark, benchmarkSkills } from "@/lib/applicant-benchmark";
import { useMyLevels } from "@/lib/my-levels";

// 공고 카드에 붙이는 한 줄 비교: 공고 기술의 합격자 평균 LV와 내 평균 LV, 가장 뒤처진 기술.
export function PassedGap({
  job,
}: {
  job: { id: string; skills?: string[]; category: string };
}) {
  const skills = benchmarkSkills(job);
  const mine = useMyLevels(skills);
  const { rows } = applicantBenchmark(job.id, skills, mine ?? undefined);
  const average = (key: "me" | "passed") =>
    Math.round(rows.reduce((sum, r) => sum + r[key], 0) / rows.length);
  const passed = average("passed");
  if (!mine)
    return (
      <p className="passed-gap">
        합격자 평균 <b>LV {passed}</b>
      </p>
    );
  const me = average("me");
  const weakest = [...rows].sort(
    (a, b) => b.passed - b.me - (a.passed - a.me),
  )[0];
  return (
    <p className={`passed-gap${me < passed ? " is-behind" : ""}`}>
      합격자 평균 <b>LV {passed}</b>, 나 <b className="is-me">LV {me}</b>
      {weakest && weakest.me < weakest.passed && (
        <span>
          {weakest.axis} LV {weakest.passed - weakest.me} 부족
        </span>
      )}
    </p>
  );
}
