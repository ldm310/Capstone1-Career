"use client";
import type { PanelProps } from "./types";
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
      <h2>주간 계획</h2>
      <p>부족한 기술을 학습, 구현, 정리로 나눠요.</p>
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
              `${skill} 코드, 설명 근거 정리하기`,
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
            setNotice("모든 기술에 코드 근거가 있어요.");
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
              "목표 지원일을 넘어요. 주당 시간이나 날짜를 조정해 주세요.",
            );
            return;
          }
          void save("tasks", { tasks: [...state.tasks, ...filtered] });
        }}
      >
        계획 추가
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
    </section>
  );
}
