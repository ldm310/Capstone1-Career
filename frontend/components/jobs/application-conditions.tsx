import type { CSSProperties } from "react";
import Link from "next/link";
import {
  Award,
  GraduationCap,
  BriefcaseBusiness,
  Info,
  Check,
  Minus,
} from "lucide-react";
import { demoMyProfile } from "@/mock/hiring-cohort";
import { qualificationScore, type JobBenchmark } from "@/lib/job-benchmark";

export function ApplicationConditions({
  benchmark,
  noComparison = false,
  onOpenPosting,
}: {
  benchmark: JobBenchmark;
  noComparison?: boolean;
  onOpenPosting: () => void;
}) {
  const synthetic = benchmark.source === "SYNTHETIC";
  const mine = synthetic ? demoMyProfile() : null;
  const score = qualificationScore(benchmark.qualifications);
  const met = benchmark.qualifications.filter(
    (item) => item.status === "met",
  ).length;
  return (
    <section
      className="application-conditions"
      aria-labelledby="conditions-title"
    >
      <header>
        <h3 id="conditions-title">지원 자격 분석</h3>
        <p>
          {noComparison
            ? "비교할 지원자 자료가 없어, 공고의 필수 조건을 기준으로 확인해요."
            : "다른 지원자와의 비교 없이 내 지원 자격을 확인해요."}
        </p>
      </header>
      {synthetic && (
        <p className="conditions-example-label">가상 공고·내 지원 정보 예시</p>
      )}
      <div className="qualification-score-panel">
        <div
          className="qualification-score-ring"
          style={{ "--score": `${score ?? 0}%` } as CSSProperties}
        >
          <div>
            <strong
              aria-label={
                score === null
                  ? "지원 자격 점수 산정 전"
                  : `지원 자격 ${score}점, 100점 만점`
              }
            >
              {score ?? "—"}
            </strong>
            <span>{score === null ? "산정 전" : "/ 100점"}</span>
          </div>
        </div>
        <div className="qualification-score-copy">
          <p className="qualification-eyebrow">나의 지원 자격</p>
          <h4>
            {score === null ? "평가 자료 미등록" : `필수 조건 ${met}개 충족`}
          </h4>
          <p>
            {score === null
              ? "공고 요건과 내 자료의 평가 결과가 연결되면 점수를 표시해요."
              : `필수 조건 ${benchmark.qualifications.length}개 중 ${met}개 충족 · ${benchmark.qualifications.length - met}개 보완`}
          </p>
          <span>필수 조건 충족도 · 합격 확률과는 달라요</span>
        </div>
      </div>
      {!!benchmark.qualifications.length && (
        <div className="qualification-checks">
          <h4>필수 조건별 확인</h4>
          <ul>
            {benchmark.qualifications.map((item) => (
              <li key={item.text}>
                {item.status === "met" ? (
                  <Check size={16} aria-hidden="true" />
                ) : (
                  <Minus size={16} aria-hidden="true" />
                )}
                <span>{item.text}</span>
                <strong data-status={item.status}>
                  {item.status === "met"
                    ? "충족"
                    : item.status === "missing"
                      ? "보완 필요"
                      : "확인 전"}
                </strong>
              </li>
            ))}
          </ul>
          <p>
            필수 조건을 같은 비중으로 계산해요. 충족 항목 ÷ 전체 필수 항목 × 100
          </p>
        </div>
      )}
      {mine ? (
        <dl className="application-condition-rows">
          <div>
            <dt>
              <Award size={20} aria-hidden="true" />
              자격증
            </dt>
            <dd>
              <span>나</span>
              <strong>{mine.certificates.length}개</strong>
              <button onClick={onOpenPosting}>공고 정보 확인</button>
            </dd>
          </div>
          <div>
            <dt>
              <GraduationCap size={20} aria-hidden="true" />
              평균 학점
            </dt>
            <dd>
              <span>나</span>
              <strong>{mine.gpa.toFixed(1)}</strong>
              <small>/ 4.5</small>
            </dd>
          </div>
          <div>
            <dt>
              <BriefcaseBusiness size={20} aria-hidden="true" />
              경력
            </dt>
            <dd>
              <span>나</span>
              <strong>{mine.career}</strong>
            </dd>
          </div>
        </dl>
      ) : (
        <div className="qualification-next">
          <Link href="/my-data">내 자료 등록하기 →</Link>
          <button onClick={onOpenPosting}>공고의 자격요건 확인</button>
        </div>
      )}
      <p className="conditions-footnote">
        <Info size={15} aria-hidden="true" />
        자격증·학점·경력은 위 점수에 합산하지 않아요.{" "}
        {synthetic && "점수와 충족 여부는 화면 확인용 예시예요."}
      </p>
    </section>
  );
}
