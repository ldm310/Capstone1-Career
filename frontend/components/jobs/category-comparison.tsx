"use client";

import { Info, UsersRound } from "lucide-react";
import {
  categoryKeywords,
  categoryLevels,
  skillCategories,
  type SkillCategoryCode,
} from "@/lib/skill-categories";
import { demoMyProfile, meanKeywordLevels } from "@/mock/hiring-cohort";
import { useMyLevels } from "@/lib/my-levels";
import type { JobBenchmark } from "@/lib/job-benchmark";

type Levels = Record<SkillCategoryCode, number>;
const center = { x: 230, y: 176 };
function point(index: number, radius: number) {
  const angle = ((index * 36 - 90) * Math.PI) / 180;
  return {
    x: center.x + Math.cos(angle) * radius,
    y: center.y + Math.sin(angle) * radius,
  };
}
function polygon(levels: number[]) {
  return levels
    .map((value, index) => {
      const p = point(index, value * 1.08);
      return `${p.x},${p.y}`;
    })
    .join(" ");
}

function ComparisonRadar({
  title,
  comparison,
  mine,
  label,
  count,
  color,
}: {
  title: string;
  comparison: Levels;
  mine: Levels;
  label: string;
  count: number;
  color: string;
}) {
  const description = skillCategories
    .map(
      (category) =>
        `${category.name}: ${label} LV ${comparison[category.code]}, 나 LV ${mine[category.code]}`,
    )
    .join(". ");
  return (
    <section className="comparison-radar-card" aria-label={title}>
      <header className="comparison-card-heading">
        <div>
          <h3>{title}</h3>
          <p>키워드 LV 평균 · 0–100</p>
        </div>
        <div className="comparison-legend" aria-label="차트 범례">
          <span>
            <i style={{ background: color }} />
            {label}
          </span>
          <span>
            <i className="legend-me" />나
          </span>
        </div>
      </header>
      <svg
        className="category-radar"
        viewBox="0 0 460 350"
        role="img"
        aria-label={description}
      >
        <title>{title}</title>
        <desc>{description}</desc>
        {[20, 40, 60, 80, 100].map((tick) => (
          <polygon
            key={tick}
            points={polygon(Array(10).fill(tick))}
            fill="none"
            stroke="#e0e8ee"
            strokeWidth="1"
          />
        ))}
        {skillCategories.map((category, index) => {
          const edge = point(index, 108),
            text = point(index, 146);
          return (
            <g key={category.code}>
              <line
                x1={center.x}
                y1={center.y}
                x2={edge.x}
                y2={edge.y}
                stroke="#e8eef3"
              />
              <text
                x={text.x}
                y={text.y - (category.label.length > 1 ? 4 : 0)}
                textAnchor={
                  Math.abs(text.x - center.x) < 8
                    ? "middle"
                    : text.x > center.x
                      ? "start"
                      : "end"
                }
                fill="#4c6172"
                fontSize="12"
                fontWeight="500"
              >
                {category.label.map((line, lineIndex) => (
                  <tspan key={line} x={text.x} dy={lineIndex ? 15 : 0}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
        {[20, 40, 60, 80, 100].map((tick) => (
          <text
            key={tick}
            x={center.x + 5}
            y={center.y - tick * 1.08 + 3}
            fontSize="8"
            fill="#8294a3"
          >
            {tick}
          </text>
        ))}
        <polygon
          points={polygon(
            skillCategories.map((category) => comparison[category.code]),
          )}
          fill={color}
          fillOpacity=".13"
          stroke={color}
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <polygon
          points={polygon(
            skillCategories.map((category) => mine[category.code]),
          )}
          fill="#69b969"
          fillOpacity=".18"
          stroke="#57a95b"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {skillCategories.map((category, index) => {
          const p = point(index, mine[category.code] * 1.08);
          return (
            <circle
              key={category.code}
              cx={p.x}
              cy={p.y}
              r="2.7"
              fill="#57a95b"
            >
              <title>
                {category.name}: 나 LV {mine[category.code]}
              </title>
            </circle>
          );
        })}
      </svg>
      <p className="comparison-sample-count">
        <UsersRound size={13} aria-hidden="true" />
        가상 {label === "합격자 평균" ? "합격자" : "지원자"} {count}명 기준
      </p>
    </section>
  );
}

export function CategoryComparison({ cohort }: { cohort: JobBenchmark }) {
  const mine = useMyLevels(categoryKeywords);
  const myLevels = categoryLevels(mine ?? demoMyProfile().keywordLevels);
  const applicants = categoryLevels(
    meanKeywordLevels(cohort.applicants, categoryKeywords),
  );
  const passed = categoryLevels(
    meanKeywordLevels(cohort.passed, categoryKeywords),
  );
  return (
    <div className="category-comparison" data-source="synthetic">
      <p className="comparison-data-note">
        <Info size={14} aria-hidden="true" />
        화면 확인용 가상 데이터예요.{!mine && " 내 LV도 예시로 표시해요."}
      </p>
      {!cohort.passed.length && (
        <div className="comparison-empty-note" role="status">
          <Info size={16} aria-hidden="true" />
          합격자 데이터가 아직 없어요.
        </div>
      )}
      <div
        className={`comparison-charts${cohort.passed.length ? "" : " is-single"}`}
      >
        {!!cohort.passed.length && (
          <ComparisonRadar
            title="합격자 vs 나 스탯"
            comparison={passed}
            mine={myLevels}
            label="합격자 평균"
            count={cohort.passed.length}
            color="#e5a348"
          />
        )}
        <ComparisonRadar
          title="경쟁자 vs 나 스탯"
          comparison={applicants}
          mine={myLevels}
          label="전체 지원자 평균"
          count={cohort.applicants.length}
          color="#6e8cde"
        />
      </div>
    </div>
  );
}
