"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Bookmark, BriefcaseBusiness, MapPin } from "lucide-react";
import { useSavedJobs, type SaveResult } from "@/lib/saved-jobs";
import { SaveFeedback } from "@/components/shared/save-feedback";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { roleLabels } from "@/lib/korean";
import { dDay } from "@/components/jobs/job-summary";
import { PassedGap } from "@/components/jobs/passed-gap";

// 저장한 공고 목록. 카드를 누르면 공고 상세로, 책갈피를 누르면 저장을 취소한다.
export function SavedJobsPanel() {
  const { jobs, toggle, error, loading, retry } = useSavedJobs();
  const [message, setMessage] = useState<SaveResult | null>(null);
  const feedback = (
    <SaveFeedback result={message} onDismiss={() => setMessage(null)} />
  );
  const [now] = useState(() => Date.now());
  if (error)
    return (
      <>
        <div className="mypage-empty" role="alert">
          <h2>저장 목록을 불러오지 못했습니다</h2>
          <p>{error}</p>
          <button
            className="career-primary"
            disabled={loading}
            onClick={() => void retry()}
          >
            다시 시도
          </button>
        </div>
        {feedback}
      </>
    );
  if (!jobs || (loading && !jobs.length)) return <LoadingSpinner inline />;
  if (!jobs.length)
    return (
      <>
        <div className="mypage-empty">
          <Bookmark size={28} aria-hidden="true" />
          <p>저장한 공고가 없어요.</p>
          <Link className="cta" href="/jobs">
            공고 보러 가기 <ArrowRight size={16} />
          </Link>
        </div>
        {feedback}
      </>
    );
  return (
    <section aria-labelledby="saved-title">
      <h2 id="saved-title" className="mypage-count">
        저장한 공고 <b>{jobs.length}</b>
      </h2>
      <ul className="mypage-jobs">
        {jobs.map((job) => {
          const left = dDay(job.closesAt, now);
          return (
            <li key={job.id} className="card-click">
              <div className="mypage-job-main">
                <small>
                  {job.company}, {roleLabels[job.category]}
                </small>
                <h3>
                  <Link
                    className="card-link"
                    href={`/jobs?job=${encodeURIComponent(job.id)}`}
                  >
                    {job.title}
                  </Link>
                </h3>
                <p>
                  <span>
                    <MapPin size={14} aria-hidden="true" />
                    {job.location}
                  </span>
                  <span>
                    <BriefcaseBusiness size={14} aria-hidden="true" />
                    {job.employment}
                  </span>
                  <span>
                    {new Date(job.savedAt).toLocaleDateString("ko-KR", {
                      month: "numeric",
                      day: "numeric",
                    })}{" "}
                    저장
                  </span>
                </p>
                <PassedGap />
              </div>
              <div className="mypage-job-side">
                {left && (
                  <b
                    className={`job-dday${left === "마감" ? " is-closed" : ""}`}
                  >
                    {left}
                  </b>
                )}
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`${job.title} 저장 취소`}
                  onClick={async () => setMessage(await toggle(job))}
                >
                  <Bookmark size={20} fill="currentColor" />
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {feedback}
    </section>
  );
}
