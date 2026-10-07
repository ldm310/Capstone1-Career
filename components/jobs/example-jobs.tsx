"use client";
import { useState } from "react";
import Link from "next/link";
import { MapPin, ArrowRight, Users } from "lucide-react";
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
import { ExampleSwitcher } from "@/components/studies/example-switcher";
import {
  applicationKey,
  useStudies,
} from "@/components/studies/study-provider";

export function ExampleJobs({ tier }: { tier: StudyTier }) {
  const { state } = useStudies();
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
          <h2>내 경험과 비교한 공고</h2>
          <p>
            자격요건을 먼저 확인하고, 이 공고에 연결되는 우대 기술을 살펴보세요.
          </p>
        </div>
        <Link href={`/studies?demo=${tier}`}>
          내 스터디 <ArrowRight size={16} />
        </Link>
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
      <p className="study-muted">
        예시 공고 {jobs.length}개 · 표시된 날짜와 조건은 화면 체험을 위한 가상
        정보예요.
      </p>
      <div className="public-job-grid">
        {jobs.map((job) => (
          <article className="public-job-card" key={job.id}>
            <QualificationSummary comparison={exampleComparison(job, tier)} />
            <div className="public-company">
              <strong>{job.company}</strong>
              <span className="official-label">예시 공고</span>
            </div>
            <h3>
              <Link href={`/jobs?job=${job.id}&demo=${tier}`}>{job.title}</Link>
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
                예시 마감 {new Date(job.closesAt!).toLocaleDateString("ko-KR")}
              </span>
              {state.applied.includes(applicationKey(job.id, tier)) && (
                <span className="study-confirmed">지원 완료 · 예시</span>
              )}
            </div>
            <Link
              className="public-job-source"
              href={`/jobs?job=${job.id}&demo=${tier}`}
            >
              비교 결과 · 지원 확인 <ArrowRight size={16} />
            </Link>
            <Link
              className="public-job-source"
              href={`/jobs?job=${job.id}&demo=${tier}&view=study`}
            >
              <Users size={16} />
              스터디 참여 신청 <ArrowRight size={16} />
            </Link>
          </article>
        ))}
      </div>
      {!jobs.length && (
        <div className="study-empty">
          조건에 맞는 예시 공고가 없어요. 필터를 바꿔보세요.
        </div>
      )}
    </div>
  );
}
