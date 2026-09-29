"use client";
import type { PanelProps } from "./types";
import Link from "next/link";
import { day } from "@/lib/workspace-selectors";
import { id } from "./helpers";
export function PlanPanel({
  state,
  busy,
  save,
  setNotice,
  setError,
  findings,
  targets,
  jobSkills,
}: Pick<
  PanelProps,
  | "state"
  | "busy"
  | "save"
  | "setNotice"
  | "setError"
  | "findings"
  | "targets"
  | "jobSkills"
>) {
  return (
    <section className="career-panel">
      <h2>주간 준비 계획</h2>
      <p>
        부족한 기술마다 학습·구현·근거 정리로 나눕니다. 각 활동은 1시간 단위
        초안이며 실제 난이도에 맞게 날짜를 조정하세요.
      </p>
      <button
        disabled={busy}
        onClick={() => {
          const missing = (jobSkills.length ? jobSkills : targets).filter(
            (s) =>
              !findings.some(
                (f) => f.skill === s && f.type === "implementation",
              ),
          );
          const created = missing
            .slice(0, 6)
            .flatMap((skill) => [
              `${skill} 공식 문서 읽고 메모하기`,
              `${skill}을 프로젝트에 구현하기`,
              `${skill} 코드·설명 근거 정리하기`,
            ])
            .map((title, i) => ({
              id: id(),
              title,
              date: day(
                Math.floor(i / state.hours) * 7 +
                  (i % Math.min(state.hours, 7)),
              ),
              done: false,
            }));
          if (!created.length) {
            setNotice(
              "선택한 기술에 코드 근거가 있습니다. 공고를 비교해 새로운 준비 항목을 찾아보세요.",
            );
            return;
          }
          const filtered = created.filter(
            (t) => !state.tasks.some((old) => old.title === t.title),
          );
          if (
            state.targetDate &&
            filtered.some((t) => t.date > state.targetDate)
          ) {
            setError(
              "계획이 목표 지원일을 넘습니다. 주당 시간을 늘리거나 목표 지원일을 조정해 주세요.",
            );
            return;
          }
          void save("tasks", { tasks: [...state.tasks, ...filtered] });
        }}
      >
        준비 조건으로 계획 추가
      </button>
      {state.tasks.map((task) => (
        <div className="career-task" key={task.id}>
          <input
            aria-label={`${task.title} 완료`}
            type="checkbox"
            disabled={busy}
            checked={task.done}
            onChange={() =>
              save("tasks", {
                tasks: state.tasks.map((t) =>
                  t.id === task.id ? { ...t, done: !t.done } : t,
                ),
              })
            }
          />
          <span>{task.title}</span>
          <input
            aria-label={`${task.title} 날짜`}
            type="date"
            value={task.date}
            disabled={busy}
            onChange={(e) =>
              save("tasks", {
                tasks: state.tasks.map((t) =>
                  t.id === task.id ? { ...t, date: e.target.value } : t,
                ),
              })
            }
          />
          <button
            disabled={busy}
            onClick={() =>
              save("tasks", {
                tasks: state.tasks.filter((t) => t.id !== task.id),
              })
            }
          >
            삭제
          </button>
        </div>
      ))}
      <p>
        활동 체크만으로 검증 근거를 만들지 않습니다. 완료 후 자료를 다시 분석해
        변화를 확인하세요.
      </p>
      <Link href="/my-skills">구현한 자료 다시 분석하기 →</Link>
    </section>
  );
}
