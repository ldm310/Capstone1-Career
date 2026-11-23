"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Bookmark, BriefcaseBusiness, MapPin } from "lucide-react";
import { roleLabels } from "@/lib/korean";
import type { PublicJob } from "@/types/public-job";

export function JobListRow({
  job,
  href,
  statsHref,
  comparison,
  isSaved = false,
  onToggle,
  showCategory = true,
  showWorkplace = true,
}: {
  job: PublicJob;
  href: string;
  statsHref: string;
  comparison: ReactNode;
  isSaved?: boolean;
  onToggle?: () => void;
  showCategory?: boolean;
  showWorkplace?: boolean;
}) {
  return (
    <article className="public-job-card job-list-row card-click">
      <div className="public-company job-list-company">
        <div className="job-list-company-name">
          <strong>{job.company}</strong>
          {job.dummy && <span className="dummy-label">예시</span>}
        </div>
        {showCategory && (
          <span className="public-job-category">
            {roleLabels[job.category]}
          </span>
        )}
      </div>
      <div className="job-list-main">
        <h3>
          <Link className="card-link" href={href} title={job.title}>
            {job.title}
          </Link>
        </h3>
        {comparison}
      </div>
      <div className="public-job-meta job-list-meta">
        <span>
          <MapPin size={15} aria-hidden="true" />
          {job.location}
        </span>
        <span>
          <BriefcaseBusiness size={15} aria-hidden="true" />
          {job.employment}
        </span>
        {showWorkplace && job.workplace && (
          <span className="job-list-workplace">{job.workplace}</span>
        )}
      </div>
      <div className="job-list-actions">
        <div className="job-list-deadline">
          {job.closesAt
            ? `${new Date(job.closesAt).toLocaleDateString("ko-KR")} 마감`
            : "마감일 미등록"}
        </div>
        <Link className="public-job-source" href={statsHref}>
          역량 분석
        </Link>
        {onToggle && (
          <button
            className="icon-button job-list-save"
            aria-label={`${job.title} ${isSaved ? "저장 취소" : "저장"}`}
            aria-pressed={isSaved}
            onClick={onToggle}
          >
            <Bookmark
              size={20}
              fill={isSaved ? "currentColor" : "none"}
              aria-hidden="true"
            />
          </button>
        )}
      </div>
    </article>
  );
}
