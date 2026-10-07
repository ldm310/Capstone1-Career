"use client";
import { ChevronDown, RotateCcw, SlidersHorizontal } from "lucide-react";
import { experienceLabels, type ExperienceKind } from "@/lib/job-filters";

export function CatalogFilters({
  sort,
  setSort,
  experience,
  setExperience,
  location,
  setLocation,
  workplace,
  setWorkplace,
  reset,
}: {
  sort: string;
  setSort: (v: string) => void;
  experience: ExperienceKind[];
  setExperience: (v: ExperienceKind[]) => void;
  location: string;
  setLocation: (v: string) => void;
  workplace: string;
  setWorkplace: (v: string) => void;
  reset: () => void;
}) {
  return (
    <div className="recruit-filter-bar">
      <label className="recruit-sort">
        <span className="sr-only">공고 정렬</span>
        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="newest">최신순</option>
          <option value="closing">마감일순</option>
        </select>
      </label>
      <details className="recruit-filter-popover">
        <summary>
          채용구분 {experience.length > 0 && <span>{experience.length}</span>}
          <ChevronDown size={16} />
        </summary>
        <fieldset>
          <legend className="sr-only">채용구분 선택</legend>
          {Object.entries(experienceLabels).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                type="checkbox"
                checked={experience.includes(key as ExperienceKind)}
                onChange={(e) =>
                  setExperience(
                    e.target.checked
                      ? [...experience, key as ExperienceKind]
                      : experience.filter((v) => v !== key),
                  )
                }
              />
            </label>
          ))}
          <p>복수 선택할 수 있어요. 구분이 확인된 공고만 표시돼요.</p>
        </fieldset>
      </details>
      <details className="recruit-filter-popover recruit-detail-filter">
        <summary>
          <SlidersHorizontal size={16} />
          상세조건
          <ChevronDown size={16} />
        </summary>
        <div className="recruit-filter-fields">
          <label>
            지역
            <input
              aria-label="지역 검색"
              placeholder="예: 서울, Seoul"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </label>
          <label>
            근무 방식
            <select
              aria-label="근무 방식"
              value={workplace}
              onChange={(e) => setWorkplace(e.target.value)}
            >
              <option value="all">전체</option>
              <option value="remote">원격</option>
              <option value="hybrid">혼합</option>
              <option value="on-site">사무실</option>
            </select>
          </label>
        </div>
      </details>
      <button
        type="button"
        className="recruit-reset"
        aria-label="필터 초기화"
        onClick={reset}
      >
        <RotateCcw size={14} />
        초기화
      </button>
    </div>
  );
}
