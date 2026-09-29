"use client";
import type { PanelProps } from "./types";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
export function OverviewPanel({
  state,
  findings,
  skills,
  gaps,
  next,
  upcoming,
  latest,
  previous,
  added,
  removed,
}: Pick<
  PanelProps,
  | "state"
  | "findings"
  | "skills"
  | "gaps"
  | "next"
  | "upcoming"
  | "latest"
  | "previous"
  | "added"
  | "removed"

>) {
  return (
    <>
      <section className="career-next">
        <span className="live-label">지금 할 일</span>
        <h2>
          {!findings.length
            ? "내 프로젝트에서 첫 역량 근거 찾기"
            : next
              ? `${next} 구현 근거 보완하기`
              : "기록을 업데이트하고 새 공고 비교하기"}
        </h2>
        <p>
          {!findings.length
            ? "GitHub 공개 저장소나 이력서를 분석하면, 어떤 기술이 어디에서 발견됐는지 확인할 수 있어요."
            : next
              ? "선택한 직무의 기본 기술 목록에서 아직 코드 근거가 없는 기술입니다. 숙련도 평가가 아닙니다."
              : "공고마다 다른 요구 조건을 내 실제 자료와 비교해 보세요."}
        </p>
        <Link
          className="career-primary"
          href={`/career?tab=${!findings.length ? "sources" : next ? "plan" : "jobs"}`}
        >
          {!findings.length
            ? "내 자료 분석하기"
            : next
              ? "준비 계획 만들기"
              : "공고 비교하기"}{" "}
          <ArrowRight size={18} />
        </Link>
      </section>
      <div className="career-stats">
        <article>
          <strong>{skills.length}</strong>
          <span>자료에서 발견된 기술</span>
        </article>
        <article>
          <strong>{gaps.length}</strong>
          <span>코드 근거를 보완할 기본 기술</span>
        </article>
        <article>
          <strong>{state.tasks.filter((t) => !t.done).length}</strong>
          <span>남은 준비 활동</span>
        </article>
        <article>
          <strong>{upcoming.length}</strong>
          <span>7일 안에 예정된 일정</span>
        </article>
      </div>
      <section className="career-panel">
        <h2>최근 분석 이후 달라진 점</h2>
        {latest ? (
          <>
            <p>
              {latest.title} · {new Date(latest.at).toLocaleString("ko-KR")}
            </p>
            <p>
              {previous
                ? "같은 자료의 이전 분석과 비교"
                : "첫 분석 — 비교 기준을 저장했어요"}
            </p>
            <div className="career-tags">
              {added.map((f) => (
                <span key={f.id}>+ {f.skill}</span>
              ))}
              {removed.map((f) => (
                <span key={f.id}>이번 분석에서 미발견 · {f.skill}</span>
              ))}
            </div>
            {previous && !added.length && !removed.length && (
              <p>기술 목록의 변화가 없습니다.</p>
            )}
            <small>
              파일 검사 범위의 변화로 미발견될 수도 있습니다. 역량이 사라졌다는
              뜻은 아닙니다.
            </small>
          </>
        ) : (
          <p>자료를 분석하면 이전 결과와의 변화가 여기에 표시됩니다.</p>
        )}
      </section>
      <section className="career-panel">
        <h2>다가오는 일정</h2>
        {upcoming.length ? (
          upcoming.map((e) => (
            <p key={e.id}>
              {e.date.replace("T", " ")} · {e.type} · {e.title}
            </p>
          ))
        ) : (
          <p>7일 이내 등록된 일정이 없습니다.</p>
        )}
        <Link href="/application-tracker?tab=schedule">일정 관리 →</Link>
      </section>
    </>
  );
}
