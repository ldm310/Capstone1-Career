"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Bookmark, BriefcaseBusiness, MapPin } from "lucide-react";
import { useSavedJobs } from "@/lib/saved-jobs";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { roleLabels } from "@/lib/korean";
import { dDay } from "@/components/jobs/job-summary";

// 저장한 공고 목록. 카드를 누르면 공고 상세로, 책갈피를 누르면 저장을 취소한다.
export function SavedJobsPanel() {
  const { jobs, toggle } = useSavedJobs();
  const [message, setMessage] = useState("");
  const [now] = useState(() => Date.now());
  if (!jobs) return <LoadingSpinner inline />;
  if (!jobs.length)
    return (
      <div className="mypage-empty">
        <Bookmark size={28} aria-hidden="true" />
        <p>저장한 공고가 없어요.</p>
        <Link className="cta" href="/jobs">
          공고 보러 가기 <ArrowRight size={16} />
        </Link>
      </div>
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
              <span className="home-job-mark" aria-hidden="true">
                {job.company.slice(0, 1)}
              </span>
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
      <span className="sr-only" role="status">
        {message}
      </span>
    </section>
  );
}
