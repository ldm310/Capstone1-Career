"use client";
import Link from "next/link";
import { type ExperienceKind } from "@/lib/job-filters";
import { CatalogFilters } from "@/components/jobs/catalog-filters";
import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { JobListRow } from "@/components/jobs/job-list-row";
import type { PublicJob, PublicJobsResponse } from "@/types/public-job";
import { roleLabels } from "@/lib/korean";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { PassedGap } from "@/components/jobs/passed-gap";
import { useSavedJobs, type SaveResult } from "@/lib/saved-jobs";
import { SaveFeedback } from "@/components/shared/save-feedback";
import { ListPagination } from "@/components/shared/list-pagination";
import {
  catalogUrl,
  jobDetailUrl,
  type CatalogState,
} from "@/lib/catalog-navigation";
export function LiveJobsSection({
  mode = "preview",
  catalog,
}: {
  mode?: "preview" | "catalog";
  catalog?: {
    state: CatalogState;
    update: (patch: Partial<CatalogState>) => void;
  };
}) {
  const preview = mode === "preview";
  const [localPageSize, setLocalPageSize] = useState(12);
  const [localLocation, setLocalLocation] = useState("");
  const [localWorkplace, setLocalWorkplace] = useState("all");
  const [localSort, setLocalSort] = useState("newest");
  const [localExperience, setLocalExperience] = useState<ExperienceKind[]>([]);
  const [feed, setFeed] = useState<PublicJobsResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [localRole, setLocalRole] = useState("all"),
    [localQuery, setLocalQuery] = useState("");
  const pageSize = catalog?.state.pageSize ?? localPageSize,
    location = catalog?.state.location ?? localLocation,
    workplace = catalog?.state.workplace ?? localWorkplace,
    sort = catalog?.state.sort ?? localSort,
    experience = catalog?.state.experience ?? localExperience,
    role = catalog?.state.role ?? localRole,
    query = catalog?.state.query ?? localQuery;
  const setPageSize = (value: number) =>
    catalog
      ? catalog.update({ pageSize: value, offset: 0 })
      : setLocalPageSize(value);
  const setLocation = (value: string) =>
    catalog
      ? catalog.update({ location: value, offset: 0 })
      : setLocalLocation(value);
  const setWorkplace = (value: string) =>
    catalog
      ? catalog.update({ workplace: value, offset: 0 })
      : setLocalWorkplace(value);
  const setSort = (value: string) =>
    catalog ? catalog.update({ sort: value, offset: 0 }) : setLocalSort(value);
  const setExperience = (value: ExperienceKind[]) =>
    catalog
      ? catalog.update({ experience: value, offset: 0 })
      : setLocalExperience(value);
  const setRole = (value: string) =>
    catalog ? catalog.update({ role: value, offset: 0 }) : setLocalRole(value);
  const setQuery = (value: string) =>
    catalog
      ? catalog.update({ query: value, offset: 0 })
      : setLocalQuery(value);
  const savedJobs = useSavedJobs();
  const [saveResult, setSaveResult] = useState<SaveResult | null>(null);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);
  const restored = useRef(false);
  const listUrl = catalog ? catalogUrl(catalog.state) : "/jobs";
  function rememberScroll() {
    try {
      sessionStorage.setItem(
        "career:catalog:scroll:" + listUrl,
        String(window.scrollY),
      );
    } catch {}
  }
  async function load(
    offset: number,
    selectedRole: string,
    term = query,
    navigate = false,
  ) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `/api/jobs?offset=${offset}&limit=${preview ? 3 : pageSize}&role=${selectedRole}&q=${encodeURIComponent(term)}&location=${encodeURIComponent(location)}&workplace=${workplace}&sort=${sort}&experience=${experience.join(",")}`,
        { signal: current.signal },
      );
      if (!response.ok) throw new Error("공고를 불러오지 못했어요.");
      const next: PublicJobsResponse = await response.json();
      if (current.signal.aborted) return;
      const lastOffset = Math.max(
        0,
        (Math.ceil(next.total / pageSize) - 1) * pageSize,
      );
      if (!preview && offset > lastOffset) {
        if (catalog) {
          catalog.update({ offset: lastOffset });
          return;
        }
        return await load(lastOffset, selectedRole, term, navigate);
      }
      setFeed(next);
      setOffset(offset);
      if (!preview && !restored.current) {
        restored.current = true;
        try {
          const key = "career:catalog:scroll:" + listUrl;
          const y = Number(sessionStorage.getItem(key));
          if (y > 0)
            requestAnimationFrame(() =>
              requestAnimationFrame(() =>
                window.scrollTo({ top: y, behavior: "instant" }),
              ),
            );
          sessionStorage.removeItem(key);
        } catch {}
      }
      if (navigate)
        document
          .getElementById("public-jobs-title")
          ?.scrollIntoView({ block: "start" });
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
      void load(catalog?.state.offset ?? 0, role, query);
    }, 350);
    return () => clearTimeout(timer);
    // load changes with input; request cancellation handles stale results.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    query,
    role,
    location,
    workplace,
    sort,
    experience,
    pageSize,
    catalog?.state.offset,
  ]);
  async function toggle(job: PublicJob) {
    setSaveResult(await savedJobs.toggle(job));
  }
  const visible = feed?.jobs ?? [];
  return (
    <section
      className={`public-jobs section-width ${preview ? "jobs-preview" : "jobs-catalog"}`}
      id="market-preview"
      aria-labelledby="public-jobs-title"
    >
      <div className="public-jobs-heading">
        <div>
          <h2 id="public-jobs-title">{preview ? "채용 공고" : "전체 공고"}</h2>
        </div>
        {preview ? (
          <Link className="feature-action" href="/jobs">
            전체 보기 →
          </Link>
        ) : null}
      </div>
      {!preview && (
        <>
          <div className="public-jobs-toolbar">
            <span className="catalog-results-label">검색</span>
            <label>
              페이지당{" "}
              <select
                aria-label="페이지당 공고 수"
                value={pageSize}
                onChange={(event) => setPageSize(Number(event.target.value))}
              >
                <option value={12}>12개</option>
                <option value={24}>24개</option>
              </select>
            </label>
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
            ? `총 ${feed.total.toLocaleString("ko-KR")}개, ${{ closing: "마감일순", newest: "최신순", company: "회사명순" }[sort]}`
            : "불러오는 중…"}
        </p>
      )}
      <div className="public-job-grid job-list">
        {(preview ? visible.slice(0, 3) : visible).map((job) => (
          <JobListRow
            key={job.id}
            job={job}
            href={jobDetailUrl(listUrl, job.id)}
            statsHref={jobDetailUrl(listUrl, job.id, true)}
            onOpen={rememberScroll}
            comparison={<PassedGap />}
            isSaved={savedJobs.isSaved(job.id)}
            onToggle={() => void toggle(job)}
          />
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
          <button onClick={() => void load(offset, role)}>다시 시도</button>
        </div>
      )}
      {!preview && feed && !error && (
        <ListPagination
          total={feed.total}
          offset={offset}
          pageSize={pageSize}
          loading={loading}
          label="채용 공고 페이지"
          onChange={(next) => {
            if (catalog) {
              catalog.update({ offset: next });
              document
                .getElementById("public-jobs-title")
                ?.scrollIntoView({ block: "start" });
            } else void load(next, role, query, true);
          }}
        />
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
      <SaveFeedback result={saveResult} onDismiss={() => setSaveResult(null)} />
    </section>
  );
}
