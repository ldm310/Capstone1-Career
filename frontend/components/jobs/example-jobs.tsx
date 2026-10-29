"use client";
import { useState } from "react";
import Link from "next/link";
import { MapPin, ArrowRight } from "lucide-react";
import {
  studyDemoJobs,
  exampleComparison,
  type StudyTier,
} from "@/lib/study-prototype";
import {
  jobExperience,
  sortPublicJobs,
  workplaceKey,
  type ExperienceKind,
} from "@/lib/job-filters";
import { QualificationSummary } from "./qualification-summary";
import { CatalogFilters } from "./catalog-filters";
import { ExampleSwitcher } from "./example-switcher";

export function ExampleJobs({ tier }: { tier: StudyTier }) {
  const [sort, setSort] = useState("newest"),
    [location, setLocation] = useState(""),
    [workplace, setWorkplace] = useState("all");
  const [experience, setExperience] = useState<ExperienceKind[]>([]);
  const jobs = sortPublicJobs(
    studyDemoJobs.filter(
      (job) =>
        (!experience.length ||
          experience.some((v) => jobExperience(job).includes(v))) &&
        job.location.includes(location) &&
        (workplace === "all" || workplaceKey(job.workplace) === workplace),
    ),
    sort,
  );
  return (
    <div className="jobs-catalog">
      <ExampleSwitcher tier={tier} />
      <div className="study-section-heading">
        <div>
          <h2>역량 비교 예시</h2>
        </div>
      </div>
      <CatalogFilters
        sort={sort}
        setSort={setSort}
        experience={experience}
        setExperience={setExperience}
        location={location}
        setLocation={setLocation}
        workplace={workplace}
        setWorkplace={setWorkplace}
        reset={() => {
          setSort("newest");
          setLocation("");
          setWorkplace("all");
          setExperience([]);
        }}
      />
      <p className="study-muted">예시 공고 {jobs.length}개</p>
      <div className="public-job-grid">
        {jobs.map((job) => (
          <article className="public-job-card card-click" key={job.id}>
            <QualificationSummary comparison={exampleComparison(job, tier)} />
            <div className="public-company">
              <strong>{job.company}</strong>
            </div>
            <h3>
              <Link
                className="card-link"
                href={`/jobs?job=${job.id}&demo=${tier}`}
              >
                {job.title}
              </Link>
            </h3>
            <div className="public-job-meta">
              <span>
                <MapPin size={15} />
                {job.location}
              </span>
              <span>{job.employment}</span>
            </div>
            <div className="public-job-bottom">
              <span>
                마감 {new Date(job.closesAt!).toLocaleDateString("ko-KR")}
              </span>
            </div>
            <Link
              className="public-job-source"
              href={`/jobs?job=${job.id}&demo=${tier}&view=compare`}
            >
              역량 비교 <ArrowRight size={16} />
            </Link>
          </article>
        ))}
      </div>
      {!jobs.length && (
        <div className="study-empty">조건에 맞는 공고가 없어요.</div>
      )}
    </div>
  );
}
