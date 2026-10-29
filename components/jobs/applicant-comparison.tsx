"use client";
import {
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  Tooltip,
} from "recharts";
import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { applicantBenchmark, benchmarkSkills } from "@/lib/applicant-benchmark";
import { useMyLevels } from "@/lib/my-levels";
import type { PublicJob } from "@/types/public-job";

const series = [
  { key: "passed", name: "합격자 평균", color: "#3b8fe0" },
  { key: "applicants", name: "전체 지원자 평균", color: "#9aa6b2" },
  { key: "me", name: "나", color: "#e8677a" },
] as const;

// 공고 상세 맨 위에 보여주는 지원자 비교. 축은 공고 기술, 값은 LV(1~100)다.
// 지원자, 합격자 평균은 공고 ID로 만든 예시 값이고, 나는 내 역량의 LV를 쓴다.
export function ApplicantComparison({ job }: { job: PublicJob }) {
  const reduced = useReducedMotion();
  // 좁은 화면에서는 축 이름이 잘리지 않게 차트를 줄인다.
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = matchMedia("(max-width: 640px)");
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const skills = benchmarkSkills(job);
  const myLevels = useMyLevels(skills);
  const { rows, applicantCount, passedCount } = applicantBenchmark(
    job.id,
    skills,
    myLevels ?? undefined,
  );
  const average = (key: "me" | "applicants" | "passed") =>
    Math.round(rows.reduce((sum, r) => sum + r[key], 0) / rows.length);
  return (
    <section className="study-requirements applicant-comparison">
      <h3>기술별 역량 비교</h3>
      <p className="applicant-headline">
        합격자 평균 <b className="is-passed">LV {average("passed")}</b>, 전체
        지원자 평균 <b>LV {average("applicants")}</b>, 나{" "}
        <b className="is-me">LV {average("me")}</b>
      </p>
      <p className="study-muted">
        지원자 {applicantCount}명, 합격자 {passedCount}명 (예시)
        {!myLevels && ", 내 자료가 없어 내 LV도 예시예요"}
      </p>
      <div
        className="applicant-radar"
        role="img"
        aria-label={rows
          .map(
            (r) =>
              `${r.axis}: 나 LV ${r.me}, 지원자 평균 LV ${r.applicants}, 합격자 평균 LV ${r.passed}`,
          )
          .join(". ")}
      >
        <ResponsiveContainer
          width="100%"
          height={narrow ? 300 : 360}
          minWidth={0}
        >
          <RadarChart data={rows} outerRadius={narrow ? "52%" : "74%"}>
            <PolarGrid gridType="polygon" stroke="#e3e8ee" />
            <PolarAngleAxis
              dataKey="axis"
              tick={{ fontSize: narrow ? 10 : 12, fill: "#4b5b68" }}
            />
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            {series.map((s) => (
              <Radar
                key={s.key}
                dataKey={s.key}
                name={s.name}
                stroke={s.color}
                fill={s.color}
                fillOpacity={s.key === "applicants" ? 0.08 : 0.15}
                strokeDasharray={s.key === "applicants" ? "4 3" : undefined}
                dot={{ r: 3, fill: s.color }}
                isAnimationActive={!reduced}
              />
            ))}
            <Tooltip formatter={(v) => `LV ${v}`} />
            <Legend wrapperStyle={{ fontSize: 13 }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <ul className="applicant-stats">
        {rows.map((r) => (
          <li key={r.axis} className={r.me < r.passed ? "is-behind" : ""}>
            <strong>LV {r.me}</strong>
            <span>{r.axis}</span>
            <small>
              합격자 LV {r.passed}, 평균 LV {r.applicants}
            </small>
          </li>
        ))}
      </ul>
    </section>
  );
}
