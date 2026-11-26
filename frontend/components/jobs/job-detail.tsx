"use client";
import { useEffect, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  studyDemoJobs,
  examplePosting,
  studyTier,
} from "@/lib/study-prototype";
import { unknownLocation, type PublicJob } from "@/types/public-job";
import { JobPosting } from "./job-posting";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { LinkLoadingIndicator } from "@/components/shared/link-loading-indicator";
import { JobExtras, JobSummary } from "./job-summary";
import { PersonalJobComparison } from "./personal-job-comparison";
import { SavedLevelRadar } from "./saved-level-radar";
import { experienceJob, experienceLevels } from "@/mock/posting-experience";
import { catalogBackUrl } from "@/lib/catalog-navigation";

export function JobDetail({
  id,
  experience = false,
}: {
  id: string;
  experience?: boolean;
}) {
  const params = useSearchParams();
  const tier = studyTier(params.get("demo"));
  const view =
    params.get("view") === "stats" ||
    (experience && params.get("view") !== "posting")
      ? "stats"
      : "posting";
  const [actual, setActual] = useState<PublicJob | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const job = experience
    ? experienceJob
    : tier
      ? studyDemoJobs.find((j) => j.id === id)
      : actual;
  useEffect(() => {
    if (tier || experience) return;
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
  }, [id, tier, retry, experience]);
  if (!job && !error && !tier) return <LoadingSpinner />;
  if (!job)
    return (
      <div className="study-empty">
        <p role="status">{error || "예시 공고가 없어요."}</p>
        {error && (
          <button onClick={() => setRetry((v) => v + 1)}>다시 시도</button>
        )}
        <Link
          href={
            tier
              ? `/jobs?demo=${tier}`
              : catalogBackUrl(new URLSearchParams(params.toString()))
          }
        >
          공고 목록
        </Link>
      </div>
    );
  function href(nextView: "stats" | "posting") {
    if (experience) return `/experience?view=${nextView}`;
    const search = new URLSearchParams(params.toString());
    search.set("view", nextView);
    search.delete("cohort");
    return `/jobs?${search}`;
  }
  function moveTab(event: KeyboardEvent<HTMLAnchorElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? "posting"
        : event.key === "End"
          ? "stats"
          : view === "posting"
            ? "stats"
            : "posting";
    const tab = document.getElementById(`job-${next}-tab`);
    tab?.focus({ preventScroll: true });
    tab?.click();
  }
  return (
    <div className="job-detail-page">
      <Link
        className="study-back"
        href={
          tier
            ? `/jobs?demo=${tier}`
            : catalogBackUrl(new URLSearchParams(params.toString()))
        }
      >
        <ArrowLeft size={16} />
        공고 목록
      </Link>
      {experience && (
        <p className="personal-comparison-note">예시 공고의 역량 분석 화면</p>
      )}
      <JobSummary job={job} allowSave={!experience} />
      <nav
        className="study-detail-tabs"
        role="tablist"
        aria-label="공고 상세 메뉴"
      >
        <Link
          id="job-posting-tab"
          role="tab"
          aria-selected={view === "posting"}
          aria-controls="job-public-content"
          tabIndex={view === "posting" ? 0 : -1}
          href={href("posting")}
          scroll={false}
          onKeyDown={moveTab}
          aria-current={view === "posting" ? "page" : undefined}
        >
          공고 내용
        </Link>
        <Link
          id="job-stats-tab"
          role="tab"
          aria-selected={view === "stats"}
          aria-controls="job-stats-panel"
          tabIndex={view === "stats" ? 0 : -1}
          href={href("stats")}
          scroll={false}
          onKeyDown={moveTab}
          aria-current={view === "stats" ? "page" : undefined}
        >
          역량 분석
          <LinkLoadingIndicator />
        </Link>
      </nav>
      <section
        id="job-public-content"
        className="job-public-content"
        role="tabpanel"
        aria-labelledby="job-posting-tab"
        hidden={view !== "posting"}
      >
        {view === "posting" && (
          <>
            <JobPosting
              job={job}
              posting={
                experience
                  ? experienceJob.posting
                  : tier
                    ? examplePosting(job)
                    : undefined
              }
            />
            {(job.location !== unknownLocation ||
              job.closesAt ||
              job.details?.company ||
              job.details?.applyMethod ||
              job.details?.documents?.length) && (
              <div className="job-additional-info">
                <JobExtras job={job} />
              </div>
            )}
          </>
        )}
      </section>
      <section
        id="job-stats-panel"
        role="tabpanel"
        aria-labelledby="job-stats-tab"
        hidden={view !== "stats"}
      >
        {view === "stats" &&
          (experience ? (
            <section
              className="personal-job-comparison"
              aria-label="역량 분석 예시"
              data-source="EXAMPLE"
            >
              <SavedLevelRadar levels={experienceLevels} />
              <div className="personal-comparison-footer">
                <Link href="/analysis">내 자료로 분석하기</Link>
              </div>
            </section>
          ) : (
            <PersonalJobComparison jobId={job.id} />
          ))}
      </section>
    </div>
  );
}
