"use client";
import type { PanelProps } from "./types";
import Link from "next/link";
import { FileText } from "lucide-react";
export function ApplicationsPanel({
  state,
  busy,
  save,
}: Pick<PanelProps, "state" | "busy" | "save">) {
  return (
    <>
      <section className="career-panel">
        <h2>이력서 원본과 버전</h2>
        <p>
          자료 분석에서 업로드한 문서를 지원 기록에 연결할 수 있습니다. 새
          버전은 새 파일로 업로드해 이전 원본을 보존하세요.
        </p>
        <Link href="/my-skills">이력서 업로드 →</Link>
        {state.documents.map((d) => (
          <div className="career-row" key={d.id}>
            <span>
              <FileText size={15} /> {d.name} · {d.at.slice(0, 10)}
            </span>
            <a href={`/api/documents/${d.id}`}>원본 내려받기</a>
          </div>
        ))}
      </section>
      <section className="career-panel">
        <h2>공고별 지원 기록</h2>
        <Link href="/jobs?tab=jobs">공고 비교 후 지원 기록 추가 →</Link>
        {!state.applications.length && <p>아직 추가한 지원 기록이 없습니다.</p>}
        {state.applications.map((a) => (
          <form
            key={a.id}
            className="finding"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              await save("applications", {
                applications: state.applications.map((old) =>
                  old.id === a.id
                    ? {
                        ...old,
                        stage: f.get("stage"),
                        resumeId: f.get("resumeId"),
                        notes: f.get("notes"),
                      }
                    : old,
                ),
              });
            }}
          >
            <h3>
              {a.company} · {a.title}
            </h3>
            <p>
              등록일 {a.date} · 등록 당시 근거:{" "}
              {a.snapshot.join(", ") || "없음"}
            </p>
            <div className="career-two">
              <label>
                진행 단계
                <select name="stage" defaultValue={a.stage}>
                  {[
                    "지원 준비",
                    "지원 완료",
                    "서류",
                    "코딩테스트",
                    "면접",
                    "최종",
                  ].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                제출 이력서 버전
                <select name="resumeId" defaultValue={a.resumeId}>
                  <option value="">선택하지 않음</option>
                  {state.documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} · {d.at.slice(0, 16)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              강조한 경험·지원 결과·면접 메모
              <textarea name="notes" defaultValue={a.notes} rows={3} />
            </label>
            <button disabled={busy}>지원 기록 저장</button>
            <Link href="/application-tracker?tab=schedule">면접·마감 일정 추가 →</Link>
          </form>
        ))}
      </section>
    </>
  );
}
