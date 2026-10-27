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
import { applicantBenchmark } from "@/lib/applicant-benchmark";

const series = [
  { key: "passed", name: "합격자 평균", color: "#3b8fe0" },
  { key: "applicants", name: "전체 지원자 평균", color: "#9aa6b2" },
  { key: "me", name: "나", color: "#e8677a" },
] as const;

// 공고 상세 맨 위에 보여주는 지원자 비교. 수치는 공고 ID로 만든 예시 값이다.
export function ApplicantComparison({ jobId }: { jobId: string }) {
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
  const { rows, applicantCount, passedCount } = applicantBenchmark(jobId);
  const average = (key: "me" | "applicants" | "passed") =>
    Math.round(rows.reduce((sum, r) => sum + r[key], 0) / rows.length);
  return (
    <section className="study-requirements applicant-comparison">
      <h3>프로젝트, 포트폴리오 역량 비교</h3>
      <p className="applicant-headline">
        합격자 평균 <b className="is-passed">{average("passed")}점</b>, 전체
        지원자 평균 <b>{average("applicants")}점</b>, 나{" "}
        <b className="is-me">{average("me")}점</b>
      </p>
      <p className="study-muted">
        지원자 {applicantCount}명, 합격자 {passedCount}명 (예시)
      </p>
      <div
        className="applicant-radar"
        role="img"
        aria-label={rows
          .map(
            (r) =>
              `${r.axis}: 나 ${r.me}, 지원자 평균 ${r.applicants}, 합격자 평균 ${r.passed}`,
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
            <Tooltip formatter={(v) => `${v}점`} />
            <Legend wrapperStyle={{ fontSize: 13 }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <ul className="applicant-stats">
        {rows.map((r) => (
          <li key={r.axis} className={r.me < r.passed ? "is-behind" : ""}>
            <strong>{r.me}점</strong>
            <span>{r.axis}</span>
            <small>
              합격자 {r.passed}, 평균 {r.applicants}
            </small>
          </li>
        ))}
      </ul>
    </section>
  );
}
