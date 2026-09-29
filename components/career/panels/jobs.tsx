"use client";
import type { PanelProps } from "./types";
import Link from "next/link";
import { JobLevelComparison } from "@/components/growth/job-level-comparison";
import { day } from "@/lib/workspace-selectors";
import { id } from "./helpers";
export function JobsPanel({
  state,
  busy,
  request,
  save,
  setNotice,
  findings,
  skills,
  params,
  jobs,
  jobsError,
}: Pick<
  PanelProps,
  | "state"
  | "busy"
  | "request"
  | "save"
  | "setNotice"
  | "findings"
  | "skills"
  | "params"
  | "jobs"
  | "jobsError"
>) {
  return (
    <>
      <section className="career-panel">
        <h2>공고의 요구 조건과 내 근거 비교</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            await request("/api/analyze", {
              kind: "job",
              url: form.get("url"),
              text: form.get("text"),
              company: form.get("company"),
              title: form.get("title"),
            });
          }}
        >
          <div className="career-two">
            <label>
              기업명
              <input name="company" maxLength={150} />
            </label>
            <label>
              공고 제목
              <input name="title" maxLength={200} />
            </label>
          </div>
          <label>
            공고 URL · Lever 자동 수집
            <input
              name="url"
              type="url"
              defaultValue={params.get("url") || ""}
              placeholder="https://jobs.lever.co/회사/공고ID"
            />
          </label>
          <label>
            또는 공고 본문 붙여넣기
            <textarea
              name="text"
              rows={5}
              maxLength={60000}
              placeholder="다른 채용 사이트는 URL을 비우고 필수·우대 조건을 포함한 공고 본문을 붙여넣으세요."
            />
          </label>
          <button disabled={busy}>내 자료와 비교하기</button>
        </form>
        <small>
          공고의 섹션 제목으로 필수·우대를 분리합니다. 판단할 수 없는 기술은
          ‘분류 미확인’에 남깁니다.
        </small>
      </section>
      {state.job && <JobLevelComparison job={state.job} />}
      {state.job && (
        <section className="career-panel">
          <span className="live-label">실제 본문 기반 · 규칙 분석</span>
          <h2>
            {state.job.company} · {state.job.title}
          </h2>
          {[
            ["필수", state.job.required],
            ["우대", state.job.preferred],
            ["분류 미확인", state.job.unknown],
          ].map(([label, list]) => (
            <div key={String(label)}>
              <h3>{String(label)}</h3>
              {(list as string[]).length ? (
                (list as string[]).map((skill) => (
                  <div className="career-row" key={skill}>
                    <strong>{skill}</strong>
                    <span>
                      {findings.some(
                        (f) => f.skill === skill && f.type === "implementation",
                      )
                        ? "코드 근거 있음"
                        : skills.includes(skill)
                          ? "문서 근거만 있음"
                          : "근거 미발견"}
                    </span>
                  </div>
                ))
              ) : (
                <p>추출된 기술이 없습니다.</p>
              )}
            </div>
          ))}
          <div className="career-actions">
            <Link className="career-primary" href="/preparation?tab=plan">
              보완 계획 세우기 →
            </Link>
            <button
              disabled={busy}
              onClick={async () => {
                if (
                  state.applications.some(
                    (a) => a.notes === `공고 분석 ${state.job!.id}`,
                  )
                ) {
                  setNotice("이미 지원 기록에 추가한 공고입니다.");
                  return;
                }
                await save("applications", {
                  applications: [
                    {
                      id: id(),
                      company: state.job!.company,
                      title: state.job!.title,
                      url: state.job!.url,
                      stage: "지원 준비",
                      date: day(),
                      resumeId: "",
                      snapshot: skills,
                      notes: `공고 분석 ${state.job!.id}`,
                    },
                    ...state.applications,
                  ],
                });
              }}
            >
              지원 기록 추가
            </button>
          </div>
          <details>
            <summary>분석한 공고 본문 보기</summary>
            <pre>{state.job.text}</pre>
          </details>
        </section>
      )}
      <section className="career-panel">
        <h2>목표 직무에 맞는 공식 공고</h2>
        <p>
          목표 직무와 지역으로 추립니다. 경력·기술 조건은 본문 비교 후
          판단하세요. 추천 순위나 적합도 점수를 만들지 않습니다.
        </p>
        {jobsError && <p role="alert">{jobsError}</p>}
        {jobs
          .filter(
            (j) =>
              j.category === state.role &&
              (!state.region || j.location.includes(state.region)),
          )
          .map((j) => (
            <article className="finding" key={j.id}>
              <h3>
                {j.company} · {j.title}
              </h3>
              <p>
                {j.location} · 추천 이유: 선택한 목표 직무와 일치
                {state.region ? " / 희망 지역과 일치" : ""}
              </p>
              <p>
                본문 언급 기술:{" "}
                {j.skills?.join(", ") || "추출된 기술 없음 — 원문 확인"}
              </p>
              <p>
                내 근거와 겹치는 기술:{" "}
                {j.skills?.filter((s) => skills.includes(s)).join(", ") ||
                  "현재 일치하는 근거 없음"}
              </p>
              <div className="career-actions">
                <Link
                  href={`/jobs?tab=jobs&url=${encodeURIComponent(j.url)}`}
                  onClick={() => {
                    const field =
                      document.querySelector<HTMLInputElement>(
                        "input[name=url]",
                      );
                    if (field) {
                      field.value = j.url;
                      field.focus();
                    }
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                >
                  이 공고 비교하기 →
                </Link>
                <a href={j.url} target="_blank" rel="noreferrer">
                  원문
                </a>
                <button
                  disabled={busy}
                  onClick={() =>
                    save("savedJobs", {
                      savedJobs: state.savedJobs.some((s) => s.id === j.id)
                        ? state.savedJobs.filter((s) => s.id !== j.id)
                        : [j, ...state.savedJobs],
                    })
                  }
                >
                  {state.savedJobs.some((s) => s.id === j.id)
                    ? "저장 취소"
                    : "내 공간에 저장"}
                </button>
              </div>
            </article>
          ))}
        {!jobsError &&
          !jobs.filter(
            (j) =>
              j.category === state.role &&
              (!state.region || j.location.includes(state.region)),
          ).length && (
            <p>
              조회 중이거나 조건에 맞는 공고가 없습니다. 아래 준비 조건에서
              지역을 비워 범위를 넓힐 수 있습니다.
            </p>
          )}
        <h3>내가 저장한 공고</h3>
        {state.savedJobs.length ? (
          state.savedJobs.map((j) => (
            <div className="career-row" key={j.id}>
              <a href={j.url} target="_blank" rel="noreferrer">
                {j.company} · {j.title}
              </a>
              <button
                disabled={busy}
                onClick={() =>
                  save("savedJobs", {
                    savedJobs: state.savedJobs.filter((s) => s.id !== j.id),
                  })
                }
              >
                삭제
              </button>
            </div>
          ))
        ) : (
          <p>저장한 공고가 없습니다.</p>
        )}
        <small>저장 당시 정보입니다. 마감 여부는 원문에서 확인하세요.</small>
      </section>
    </>
  );
}
