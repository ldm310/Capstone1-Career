"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import {
  studyDemoJobs,
  examplePosting,
  studyTier,
} from "@/lib/study-prototype";
import type { PublicJob } from "@/types/public-job";
import { JobPosting } from "./job-posting";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { JobExtras, JobSummary } from "./job-summary";
import { PersonalJobComparison } from "./personal-job-comparison";

export function JobDetail({ id }: { id: string }) {
  const params = useSearchParams();
  const tier = studyTier(params.get("demo"));
  const view = params.get("view") === "stats" ? "stats" : "posting";
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
  function href(nextView: "stats" | "posting") {
    const search = new URLSearchParams(params.toString());
    search.set("view", nextView);
    search.delete("cohort");
    return `/jobs?${search}#${nextView === "posting" ? "job-public-content" : "job-personal-comparison"}`;
  }
  return (
    <div className="job-detail-page">
      <Link className="study-back" href={tier ? `/jobs?demo=${tier}` : "/jobs"}>
        <ArrowLeft size={16} />
        공고 목록
      </Link>
      <JobSummary job={job} />
      <nav className="study-detail-tabs" aria-label="공고 상세 메뉴">
        <Link
          href={href("posting")}
          aria-current={view === "posting" ? "page" : undefined}
        >
          공고 내용
        </Link>
        <Link
          href={href("stats")}
          aria-current={view === "stats" ? "page" : undefined}
        >
          역량 비교
        </Link>
      </nav>
      <section
        id="job-public-content"
        className="job-public-content"
        aria-labelledby="job-public-title"
      >
        <h3 id="job-public-title">공고 내용</h3>
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
      </section>
      <PersonalJobComparison jobId={job.id} />
    </div>
  );
}
