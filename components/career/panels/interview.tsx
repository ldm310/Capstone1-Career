"use client";
import type { PanelProps } from "./types";
export function InterviewPanel({
  state,
  busy,
  save,
  questions,
}: Pick<PanelProps, "state" | "busy" | "save" | "questions">) {
  return (
    <section className="career-panel">
      <h2>면접 준비</h2>
      <p>
        {state.job
          ? `${state.job.company} 공고의 기술로 만든 질문이에요.`
          : "목표 직무의 기본 기술로 만든 질문이에요."}
      </p>
      {questions.map((q) => (
        <form
          key={q.key}
          className="finding"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void save("answers", {
              answers: {
                ...state.answers,
                [q.key]: String(f.get("answer")),
              },
            });
          }}
        >
          <h3>{q.text}</h3>
          {q.evidence ? (
            <p>
              근거:{" "}
              <a href={q.evidence.url} target="_blank" rel="noreferrer">
                {q.evidence.title} ↗
              </a>
            </p>
          ) : (
            <p>관련 근거가 없어요. 학습한 내용과 계획을 나눠 답해 보세요.</p>
          )}
          <label>
            상황, 역할, 선택 이유, 결과
            <textarea
              name="answer"
              rows={4}
              defaultValue={state.answers[q.key] || ""}
              maxLength={10000}
            />
          </label>
          <button disabled={busy}>답변 저장</button>
        </form>
      ))}
    </section>
  );
}
