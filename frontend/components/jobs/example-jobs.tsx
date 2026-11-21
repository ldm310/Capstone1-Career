"use client";
import { useState } from "react";
import { JobListRow } from "./job-list-row";
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
      <div className="public-job-grid job-list">
        {jobs.map((job) => (
          <JobListRow
            key={job.id}
            job={job}
            href={`/jobs?job=${job.id}&demo=${tier}`}
            statsHref={`/jobs?job=${job.id}&demo=${tier}&view=stats`}
            comparison={
              <QualificationSummary comparison={exampleComparison(job, tier)} />
            }
            showCategory={false}
            showWorkplace={false}
          />
        ))}
      </div>
      {!jobs.length && (
        <div className="study-empty">조건에 맞는 공고가 없어요.</div>
      )}
    </div>
  );
}
