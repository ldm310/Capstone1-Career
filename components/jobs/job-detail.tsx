"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  CircleX,
  ExternalLink,
  MapPin,
} from "lucide-react";
import {
  studyDemoJobs,
  exampleComparison,
  studyTier,
  type Requirement,
} from "@/lib/study-prototype";
import type { PublicJob } from "@/types/public-job";
import { QualificationSummary } from "./qualification-summary";
import { ExampleSwitcher } from "@/components/studies/example-switcher";
import { ApplicationConfirmation } from "@/components/studies/application-confirmation";
import { StudyOffers } from "@/components/studies/study-offers";

function RequirementList({
  title,
  rows,
}: {
  title: string;
  rows: Requirement[];
}) {
  return (
    <section className="study-requirements">
      <h3>{title}</h3>
      {rows.map((row, i) => (
        <div className="study-requirement-row" key={i}>
          {row.satisfied ? <CheckCircle2 size={19} /> : <CircleX size={19} />}
          <div>
            <strong>{row.text}</strong>
            <p>{row.evidence}</p>
          </div>
          <span className={row.satisfied ? "study-positive" : "study-negative"}>
            {row.satisfied ? "만족" : "불만족"}
            {row.level && (
              <small>
                내 {row.skill} LV{row.level}
              </small>
            )}
          </span>
        </div>
      ))}
    </section>
  );
}
export function JobDetail({ id }: { id: string }) {
  const params = useSearchParams();
  const tier = studyTier(params.get("demo"));
  const view = params.get("view") === "study" ? "study" : "comparison";
  const [actual, setActual] = useState<PublicJob | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const job = tier ? studyDemoJobs.find((j) => j.id === id) : actual;
  useEffect(() => {
    if (tier) return;
    const controller = new AbortController();
    fetch(`/api/jobs?id=${encodeURIComponent(id)}&limit=1`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("공고를 불러오지 못했어요.");
        const data = await response.json();
        if (!data.jobs?.[0])
          throw new Error(
            "현재 목록에서 공고를 찾지 못했어요. 마감되었거나 목록이 변경됐을 수 있어요.",
          );
        setActual(data.jobs[0]);
        setError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [id, tier, retry]);
  if (!job)
    return (
      <div className="study-empty">
        <p role="status">
          {error ||
            (tier ? "예시 공고를 찾지 못했어요." : "공고를 불러오고 있어요…")}
        </p>
        {error && (
          <button onClick={() => setRetry((v) => v + 1)}>다시 시도</button>
        )}
        <Link href={tier ? `/jobs?demo=${tier}` : "/jobs"}>공고 목록으로</Link>
      </div>
    );
  const comparison = tier ? exampleComparison(job, tier) : undefined;
  const base = `/jobs?job=${encodeURIComponent(job.id)}${tier ? `&demo=${tier}` : ""}`;
  return (
    <div className="job-detail-page">
      {tier && <ExampleSwitcher tier={tier} />}
      <Link className="study-back" href={tier ? `/jobs?demo=${tier}` : "/jobs"}>
        <ArrowLeft size={16} />
        공고 목록으로
      </Link>
      <header className="study-job-heading">
        <div>
          <span>{job.company}</span>
          <h2>{job.title}</h2>
          <p>
            <MapPin size={16} />
            {job.location} · {job.employment}
          </p>
        </div>
        {!tier && (
          <a href={job.url} target="_blank" rel="noopener noreferrer">
            원문 보기 <ExternalLink size={16} />
          </a>
        )}
      </header>
      <QualificationSummary comparison={comparison} />
      <ApplicationConfirmation
        key={`${job.id}:${tier}`}
        job={job}
        tier={tier}
      />
      <nav className="study-detail-tabs" aria-label="공고 상세 메뉴">
        <Link
          href={base}
          aria-current={view === "comparison" ? "page" : undefined}
        >
          자격요건·우대사항
        </Link>
        <Link
          href={`${base}&view=study`}
          aria-current={view === "study" ? "page" : undefined}
        >
          스터디
        </Link>
      </nav>
      {view === "study" ? (
        <StudyOffers job={job} tier={tier} />
      ) : comparison ? (
        <>
          <RequirementList title="자격요건" rows={comparison.required} />
          <RequirementList title="우대사항" rows={comparison.preferred} />
          <p className="study-muted">
            이 화면의 만족·불만족과 LV는 체험용 결과예요. 실제 공고의
            요구사항이나 기업의 판정이 아니에요.
          </p>
          <Link className="study-primary" href={`${base}&view=study`}>
            나에게 맞는 스터디 보기
          </Link>
        </>
      ) : (
        <section className="study-empty">
          <h3>공고별 비교 결과를 기다리고 있어요</h3>
          <p>
            자료 미확인을 불만족으로 표시하지 않아요. 실제 LV와 조건 판정은 기준
            확정 후 연결돼요.
          </p>
          <Link
            className="study-primary"
            href={`/jobs?tab=jobs&url=${encodeURIComponent(job.url)}`}
          >
            내 자료와 공고 본문 확인하기
          </Link>
        </section>
      )}
    </div>
  );
}
