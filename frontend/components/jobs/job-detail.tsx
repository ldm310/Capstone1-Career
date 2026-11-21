"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ChevronDown, ExternalLink } from "lucide-react";
import {
  studyDemoJobs,
  examplePosting,
  studyTier,
} from "@/lib/study-prototype";
import type { PublicJob } from "@/types/public-job";
import { JobPosting } from "./job-posting";
import { CategoryComparison } from "./category-comparison";
import { ApplicationConditions } from "./application-conditions";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { JobExtras, JobSummary } from "./job-summary";
import { useJobBenchmark } from "@/lib/use-job-benchmark";
import { KeywordLevels } from "./keyword-levels";

export function JobDetail({ id }: { id: string }) {
  const params = useSearchParams();
  const tier = studyTier(params.get("demo"));
  const view = params.get("view") === "conditions" ? "conditions" : "stats";
  const benchmark = useJobBenchmark(id);
  const original = useRef<HTMLDetailsElement>(null);
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
  function href(nextView: "stats" | "conditions") {
    const search = new URLSearchParams(params.toString());
    search.set("view", nextView);
    search.delete("cohort");
    return `/jobs?${search}`;
  }
  function openPosting() {
    if (original.current) {
      original.current.open = true;
      original.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  const conditionsOnly =
    !!benchmark.data &&
    !benchmark.data.passed.length &&
    !benchmark.data.applicants.length;
  const selectedView = conditionsOnly ? "conditions" : view;
  return (
    <div className="job-detail-page">
      <Link className="study-back" href={tier ? `/jobs?demo=${tier}` : "/jobs"}>
        <ArrowLeft size={16} />
        공고 목록
      </Link>
      <JobSummary job={job} />
      <nav className="study-detail-tabs" aria-label="공고 상세 메뉴">
        <Link
          href={href("stats")}
          aria-current={selectedView === "stats" ? "page" : undefined}
        >
          스탯 분석
        </Link>
        <Link
          href={href("conditions")}
          aria-current={selectedView === "conditions" ? "page" : undefined}
        >
          지원 조건
        </Link>
      </nav>
      {benchmark.error ? (
        <div className="comparison-message" role="alert">
          {benchmark.error}
          <button onClick={benchmark.retry}>다시 시도</button>
        </div>
      ) : !benchmark.data ? (
        <p className="comparison-message" role="status">
          비교 자료를 불러오는 중이에요.
        </p>
      ) : selectedView === "conditions" ? (
        <ApplicationConditions
          benchmark={benchmark.data}
          noComparison={conditionsOnly}
          onOpenPosting={openPosting}
        />
      ) : (
        <CategoryComparison cohort={benchmark.data} />
      )}
      <KeywordLevels jobId={job.id} />
      <details className="job-original-panel" ref={original}>
        <summary>
          공고 내용 보기
          <ChevronDown size={17} aria-hidden="true" />
        </summary>
        <div className="job-source-row">
          {job.dummy || job.url ? (
            <a
              className="job-original-link"
              href={
                job.dummy ? `/postings/${encodeURIComponent(job.id)}` : job.url
              }
              target="_blank"
              rel="noopener noreferrer"
            >
              원문 보기
              <ExternalLink size={13} aria-hidden="true" />
              <span className="sr-only"> (새 창)</span>
            </a>
          ) : (
            <p className="original-missing">원문을 찾을 수 없습니다.</p>
          )}
        </div>
        <JobPosting
          job={job}
          posting={tier ? examplePosting(job) : undefined}
        />
        <JobExtras job={job} />
      </details>
    </div>
  );
}
