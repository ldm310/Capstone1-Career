"use client";
import Link from "next/link";
import {
  workplaceKey,
  jobExperience,
  sortPublicJobs,
  type ExperienceKind,
} from "@/lib/job-filters";
import { CatalogFilters } from "@/components/jobs/catalog-filters";
import { useEffect, useRef, useState } from "react";
import {
  Bookmark,
  BriefcaseBusiness,
  MapPin,
  RefreshCw,
  Search,
} from "lucide-react";
import type { PublicJob, PublicJobsResponse } from "@/types/public-job";
import { isSupportedRole } from "@/lib/roles";
import { roleLabels } from "@/lib/korean";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { OriginalLink } from "@/components/jobs/original-link";
import { PassedGap } from "@/components/jobs/passed-gap";
import { useSavedJobs } from "@/lib/saved-jobs";
export function LiveJobsSection({
  mode = "preview",
}: {
  mode?: "preview" | "catalog";
}) {
  const preview = mode === "preview";
  const [location, setLocation] = useState("");
  const [workplace, setWorkplace] = useState("all");
  const [sort, setSort] = useState("newest");
  const [experience, setExperience] = useState<ExperienceKind[]>([]);
  const [feed, setFeed] = useState<PublicJobsResponse | null>(null);
  const [role, setRole] = useState("all"),
    [query, setQuery] = useState("");
  const savedJobs = useSavedJobs();
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);
  async function load(offset: number, selectedRole: string, term = query) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `/api/jobs?offset=${offset}&limit=${preview ? 3 : 12}&role=${selectedRole}&q=${encodeURIComponent(term)}&location=${encodeURIComponent(location)}&workplace=${workplace}&sort=${sort}&experience=${experience.join(",")}`,
        { signal: current.signal },
      );
      if (!response.ok) throw new Error("공고를 불러오지 못했어요.");
      const next: PublicJobsResponse = await response.json();
      if (current.signal.aborted) return;
      setFeed((previous) => ({
        ...next,
        jobs:
          offset && previous
            ? [
                ...new Map(
                  [...previous.jobs, ...next.jobs].map((job) => [job.id, job]),
                ).values(),
              ]
            : next.jobs,
      }));
      setMessage(`${next.jobs.length}개 공고를 불러왔어요.`);
    } catch (reason) {
      if (!current.signal.aborted)
        setError(
          reason instanceof Error ? reason.message : "연결을 확인해 주세요.",
        );
    } finally {
      if (!current.signal.aborted) setLoading(false);
    }
  }
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load(0, role, query);
    }, 350);
    return () => clearTimeout(timer);
    // load changes with input; request cancellation handles stale results.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, role, location, workplace, sort, experience]);
  async function toggle(job: PublicJob) {
    setMessage(await savedJobs.toggle(job));
  }
  const visible = sortPublicJobs(
    (feed?.jobs ?? []).filter(
      (job) =>
        isSupportedRole(job.category) &&
        (role === "all" || job.category === role) &&
        (!experience.length ||
          experience.some((value) => jobExperience(job).includes(value))) &&
        `${job.company} ${job.title} ${(job.skills || []).join(" ")} ${roleLabels[job.category]}`
          .toLowerCase()
          .includes(query.toLowerCase()) &&
        (!location ||
          job.location.toLowerCase().includes(location.toLowerCase())) &&
        (workplace === "all" || workplaceKey(job.workplace) === workplace),
    ),
    sort,
  );
  return (
    <section
      className={`public-jobs section-width ${preview ? "jobs-preview" : "jobs-catalog"}`}
      id="market-preview"
      aria-labelledby="public-jobs-title"
    >
      <div className="public-jobs-heading">
        <div>
          <h2 id="public-jobs-title">
            {preview ? "채용공고" : "전체 공고"}
          </h2>
        </div>
        {preview ? (
          <Link className="feature-action" href="/jobs">
            전체 보기 →
          </Link>
        ) : (
          <span className="public-source-note">
            채널코퍼레이션, 매치그룹 제공
          </span>
        )}
      </div>
      {!preview && (
        <>
          <aside className="study-preview-invite">
            <strong>역량 비교 예시</strong>
            <Link href="/jobs?demo=low">예시 보기 →</Link>
          </aside>
          <div className="public-jobs-toolbar">
            <span className="catalog-results-label">
              검색
            </span>
            <div className="public-job-filters">
              <select
                aria-label="공고 직무"
                value={role}
                onChange={(event) => {
                  setRole(event.target.value);
                  setFeed(null);
                }}
              >
                <option value="all">모든 직무</option>
                {Object.entries(roleLabels).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
              <label>
                <Search size={17} />
                <input
                  aria-label="전체 연동 공고 검색"
                  placeholder="회사, 직무, 기술"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
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
              setQuery("");
              setRole("all");
              setLocation("");
              setWorkplace("all");
              setSort("newest");
              setExperience([]);
            }}
          />
        </>
      )}
      {!preview && (
        <p className="public-feed-count">
          {feed
            ? `전체 ${feed.total}개 중 ${feed.jobs.length}개, ${sort === "closing" ? "마감일순" : "최신순"}`
            : "불러오는 중…"}
        </p>
      )}
      <div className="public-job-grid">
        {(preview ? visible.slice(0, 3) : visible).map((job) => (
          <article className="public-job-card card-click" key={job.id}>
            <div className="public-company">
              <span className="public-company-mark" aria-hidden="true">
                {job.company.slice(0, 1)}
              </span>
              <strong>{job.company}</strong>
              {job.dummy && <span className="dummy-label">예시</span>}
            </div>
            <span className="public-job-category">
              {roleLabels[job.category]}
            </span>
            <h3>
              <Link
                className="card-link"
                href={`/jobs?job=${encodeURIComponent(job.id)}`}
              >
                {job.title}
              </Link>
            </h3>
            <div className="public-job-meta">
              <span>
                <MapPin size={15} />
                {job.location}
              </span>
              <span>
                <BriefcaseBusiness size={15} />
                {job.employment}
              </span>
              {job.workplace && <span>{job.workplace}</span>}
            </div>
            <PassedGap job={job} />
            <div className="public-job-bottom">
              <span>
                {job.closesAt
                  ? `${new Date(job.closesAt).toLocaleDateString("ko-KR")} 마감`
                  : "마감일 원문 확인"}
              </span>
              <button
                className="icon-button"
                aria-label={`${job.title} ${savedJobs.isSaved(job.id) ? "저장 취소" : "저장"}`}
                aria-pressed={savedJobs.isSaved(job.id)}
                onClick={() => void toggle(job)}
              >
                <Bookmark
                  size={21}
                  fill={savedJobs.isSaved(job.id) ? "currentColor" : "none"}
                />
              </button>
            </div>
            <OriginalLink
              job={job}
              className="public-job-source public-job-original"
            />
            <Link
              className="public-job-source"
              href={`/jobs?job=${encodeURIComponent(job.id)}&view=compare`}
            >
              역량 비교 →
            </Link>
          </article>
        ))}
      </div>
      {loading && !feed && <LoadingSpinner inline />}
      {!loading && !error && !visible.length && (
        <div className="public-job-empty">
          <h3>조건에 맞는 공고가 없어요.</h3>
          <button
            onClick={() => {
              setQuery("");
              setRole("all");
              setLocation("");
              setWorkplace("all");
              setExperience([]);
            }}
          >
            검색 초기화
          </button>
        </div>
      )}
      {error && (
        <div className="public-job-empty" role="alert">
          <p>{error}</p>
          <button onClick={() => void load(feed?.nextOffset ?? 0, role)}>
            다시 시도
          </button>
        </div>
      )}
      {!preview && (
        <div className="public-job-more">
          {feed?.nextOffset != null ? (
            <button
              disabled={loading}
              onClick={() => void load(feed.nextOffset!, role)}
            >
              <RefreshCw size={19} className={loading ? "spin" : ""} />
              {loading ? "불러오는 중…" : "더보기"}
            </button>
          ) : feed && !loading && !error ? (
            <>
              <p>모든 공고를 확인했어요.</p>
              <button onClick={() => void load(0, role)}>
                <RefreshCw size={18} />
                새로고침
              </button>
            </>
          ) : null}
        </div>
      )}
      {!preview && (
        <div className="public-jobs-disclosure">
          <span>
            {feed &&
              `마지막 확인 ${new Date(feed.checkedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}`}
          </span>
        </div>
      )}
      <span className="sr-only" role="status">
        {message}
      </span>
    </section>
  );
}
