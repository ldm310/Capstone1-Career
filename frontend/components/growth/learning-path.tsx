"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, Plus } from "lucide-react";
import { learningPaths } from "@/lib/growth/learning-path";
import { levelNames, requirement } from "@/lib/growth/catalog";
import type { SkillReview, GrowthTask, Level } from "@/types/growth";

export function LearningPath({
  role,
  reviews,
  tasks,
  onSelect,
}: {
  role: string;
  reviews: SkillReview[];
  tasks: GrowthTask[];
  onSelect: (skill: string) => void;
}) {
  const path = learningPaths[role] || learningPaths.data;
  const groups = [
    ...path.stages.map((s, index) => ({
      title: s.title,
      description: s.description,
      items: s.items.filter((i) => i.skill !== "MCP"),
      kind: index === 0 ? "기초" : "심화",
    })),
    {
      title: "배포와 확장",
      description: "실행 환경을 함께 준비해요.",
      items: [path.parallel],
      kind: "병행, 선택",
    },
  ].filter((g) => g.items.length);
  const [choice, setChoice] = useState("");
  const [expanded, setExpanded] = useState<number | null>(0);
  const all = groups.flatMap((g) => g.items);
  const item = all.find((i) => i.skill === choice) || all[0];
  const groupIndex = groups.findIndex((g) =>
    g.items.some((i) => i.skill === item.skill),
  );
  const review = reviews.find((r) => r.skill === item.skill);
  const next = ((review?.level || 0) + 1) as Level;
  const task = tasks.find(
    (t) => t.skill === item.skill && t.status !== "completed",
  );

  const details =
    item.skill === "Python"
      ? [
          ["기초 문법 이해", "변수, 자료형, 조건문, 반복문"],
          ["데이터 다루기", "리스트, 딕셔너리, 파일 처리"],
          ["실습으로 익히기", "작은 예제로 직접 실행해 보기"],
        ]
      : [
          ["기초 사용", requirement(item.skill, 1)],
          ["프로젝트 적용", requirement(item.skill, 2)],
          ["개선, 문제 해결", requirement(item.skill, 3)],
        ];
  const selectedDetail = (
    <div className="focus-task" aria-live="polite">
      <div className="focus-task-main">
        <div className="focus-task-intro">
          <span className="focus-task-icon">
            <span>{groupIndex + 1}</span>
          </span>
          <div>
            <span className="learning-path-label">{item.skill}</span>
            <h3>{item.title}</h3>
            <p>{groups[groupIndex].description}</p>
          </div>
        </div>
        {groups[groupIndex].items.length > 1 && (
          <div
            className="focus-skill-picker"
            aria-label="이 단계에서 준비할 기술"
          >
            {groups[groupIndex].items.map((x) => (
              <button
                type="button"
                key={x.skill}
                aria-pressed={x.skill === item.skill}
                onClick={() => setChoice(x.skill)}
              >
                {x.skill}
                {x.optional ? " (선택)" : ""}
              </button>
            ))}
          </div>
        )}
        <div className="focus-outcomes">
          {details.map(([title, text], i) => {
            return (
              <div key={title}>
                <span className="focus-outcome-number">
                  {item.skill === "Python" ? i + 1 : `LV${i + 1}`}
                </span>
                <div>
                  <strong>{title}</strong>
                  <p>{text}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="focus-task-status">
        <div>
          <small>현재 수준</small>
          <strong>
            {review?.level
              ? `LV${review.level} ${levelNames[review.level]}`
              : "자료 확인 필요"}
          </strong>
        </div>
        <div className="focus-next">
          <small>{task ? "진행 중 과제" : "다음 과제"}</small>
          <div>
            <strong>
              {task
                ? `LV${task.level} ${levelNames[task.level]}`
                : next <= 3
                  ? `LV${next} ${levelNames[next]}`
                  : "LV3 완료"}
            </strong>
          </div>
        </div>
        <button
          className="focus-task-cta"
          type="button"
          onClick={() => onSelect(item.skill)}
        >
          {next <= 3 ? "과제 보기" : "근거 보기"}{" "}
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
  return (
    <section className="learning-path" aria-labelledby="learning-path-title">
      <div className="learning-path-heading">
        <div>
          <div className="learning-path-title">
            <h2 id="learning-path-title">학습 경로</h2>
            <span className="learning-path-label">{path.role}</span>
          </div>
          <p>
            {reviews.length
              ? "익숙한 기술은 건너뛰어도 돼요."
              : "자료를 추가하면 현재 수준이 표시돼요."}
          </p>
        </div>
        <Link className="learning-path-source" href="/my-data">
          <Plus size={16} aria-hidden="true" /> 자료 추가
        </Link>
      </div>
      <ol className="focus-path-steps" aria-label="추천 준비 순서">
        {groups.map((g, i) => (
          <li key={g.title}>
            <button
              type="button"
              aria-pressed={expanded === i}
              aria-controls={`path-panel-${i}`}
              onClick={() => {
                setChoice(g.items[0].skill);
                setExpanded(i);
              }}
            >
              <span className="focus-step-number">{i + 1}</span>
              <span>
                <strong>
                  {g.items
                    .map((x) =>
                      x.skill === "Docker"
                        ? "Docker (병행)"
                        : x.optional
                          ? `${x.skill} (선택)`
                          : x.skill,
                    )
                    .join(" + ")}
                </strong>
                <small>{g.title}</small>
              </span>
            </button>
          </li>
        ))}
      </ol>
      <div className="focus-later focus-fixed-steps">
        {groups.map((g, i) => (
          <section key={g.title} className="focus-fixed-step">
            <h3 className="focus-step-heading">
              <button
                type="button"
                id={`path-step-${i}`}
                className="focus-step-toggle"
                aria-expanded={expanded === i}
                aria-controls={`path-panel-${i}`}
                onClick={() => {
                  if (expanded === i) setExpanded(null);
                  else {
                    setChoice(g.items[0].skill);
                    setExpanded(i);
                  }
                }}
              >
                <span className="focus-step-number">{i + 1}</span>
                <span className="focus-later-label">{g.kind}</span>
                <strong>{g.title}</strong>
                <span className="focus-later-skills">
                  {g.items.map((x) => x.skill).join(", ")}
                </span>
                <span className="focus-later-description">{g.description}</span>
                <ChevronDown
                  size={18}
                  className="focus-chevron"
                  aria-hidden="true"
                />
              </button>
            </h3>
            <div
              id={`path-panel-${i}`}
              role="region"
              aria-labelledby={`path-step-${i}`}
              hidden={expanded !== i}
            >
              {expanded === i && selectedDetail}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
