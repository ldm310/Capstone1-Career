"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, CircleX } from "lucide-react";
import {
  studyDemoJobs,
  exampleComparison,
  examplePosting,
  studyTier,
  type Requirement,
} from "@/lib/study-prototype";
import type { PublicJob } from "@/types/public-job";
import { QualificationSummary } from "./qualification-summary";
import { ExampleSwitcher } from "./example-switcher";
import { JobSkillComparison } from "./job-skill-comparison";
import { JobPosting } from "./job-posting";
import { ApplicantComparison } from "./applicant-comparison";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { JobExtras, JobSummary } from "./job-summary";

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
  const view = params.get("view") === "compare" ? "compare" : "posting";
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
          throw new Error("공고를 찾지 못했어요. 마감되었을 수 있어요.");
        setActual(data.jobs[0]);
        setError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [id, tier, retry]);
  if (!job && !error && !tier) return <LoadingSpinner />;
  if (!job)
    return (
      <div className="study-empty">
        <p role="status">{error || "예시 공고가 없어요."}</p>
        {error && (
          <button onClick={() => setRetry((v) => v + 1)}>다시 시도</button>
        )}
        <Link href={tier ? `/jobs?demo=${tier}` : "/jobs"}>공고 목록</Link>
      </div>
    );
  const comparison = tier ? exampleComparison(job, tier) : undefined;
  const base = `/jobs?job=${encodeURIComponent(job.id)}${tier ? `&demo=${tier}` : ""}`;
  return (
    <div className="job-detail-page">
      {tier && <ExampleSwitcher tier={tier} />}
      <Link className="study-back" href={tier ? `/jobs?demo=${tier}` : "/jobs"}>
        <ArrowLeft size={16} />
        공고 목록
      </Link>
      <JobSummary job={job} />
      <ApplicantComparison jobId={job.id} />
      <nav className="study-detail-tabs" aria-label="공고 상세 메뉴">
        <Link
          href={base}
          aria-current={view === "posting" ? "page" : undefined}
        >
          공고 내용
        </Link>
        <Link
          href={`${base}&view=compare`}
          aria-current={view === "compare" ? "page" : undefined}
        >
          역량 비교
        </Link>
      </nav>
      {view === "posting" ? (
        <>
          <JobPosting
            job={job}
            posting={tier ? examplePosting(job) : undefined}
          />
          <JobExtras job={job} />
        </>
      ) : comparison ? (
        <>
          <QualificationSummary comparison={comparison} />
          <RequirementList title="자격요건" rows={comparison.required} />
          <RequirementList title="우대사항" rows={comparison.preferred} />
          <p className="study-muted">예시 결과예요.</p>
        </>
      ) : (
        <JobSkillComparison job={job} />
      )}
    </div>
  );
}
