"use client";
import { useEffect, useState } from "react";
import {
  Building2,
  CalendarClock,
  Info,
  MapPin,
  Star,
  TrainFront,
} from "lucide-react";
import { unknownLocation, type PublicJob } from "@/types/public-job";
import { experienceLabels, jobExperience } from "@/lib/job-filters";
import { useSavedJobs } from "@/lib/saved-jobs";
import { OriginalLink } from "./original-link";

const dayMs = 86400000;
// 마감까지 남은 날짜. 마감일이 없으면 null, 지났으면 "마감".
export function dDay(closesAt: string | null | undefined, now: number) {
  if (!closesAt) return null;
  const left = Date.parse(closesAt) - now;
  if (left < 0) return "마감";
  const days = Math.floor(left / dayMs);
  return days === 0 ? "D-Day" : `D-${days}`;
}
const dateTime = (value: string) =>
  new Date(value).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  });

function Rows({ rows }: { rows: [string, string | undefined | null][] }) {
  const shown = rows.filter(([, v]) => v);
  if (!shown.length) return null;
  return (
    <dl className="job-info-rows">
      {shown.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

// 공고 상세 맨 위 요약: 회사, 제목, 저장, 지원 버튼과 핵심 조건 표.
export function JobSummary({ job }: { job: PublicJob }) {
  const saved = useSavedJobs();
  const [message, setMessage] = useState("");
  const [now] = useState(() => Date.now());
  const d = job.details ?? {};
  const left = dDay(job.closesAt, now);
  const isSaved = saved.isSaved(job.id);
  const experience = jobExperience(job)
    .map((k) => experienceLabels[k])
    .join(", ");
  return (
    <header className="job-summary">
      <div className="job-summary-top">
        <div className="job-summary-title">
          <span className="job-summary-company">
            {job.company}
            {job.dummy && <small className="dummy-label">예시</small>}
          </span>
          <h2>{job.title}</h2>
        </div>
        <div className="job-summary-actions">
          <button
            type="button"
            className="plain-button job-save"
            aria-pressed={isSaved}
            aria-label={isSaved ? "공고 저장 취소" : "공고 저장"}
            onClick={async () => setMessage(await saved.toggle(job))}
          >
            <Star size={22} fill={isSaved ? "currentColor" : "none"} />
            <span>{isSaved ? "저장됨" : "저장"}</span>
          </button>
          <div className="job-apply">
            {left && (
              <b className={`job-dday${left === "마감" ? " is-closed" : ""}`}>
                {left}
              </b>
            )}
            <OriginalLink
              job={job}
              className="job-original-link"
              label={d.applyMethod ?? "원문에서 지원"}
            />
          </div>
        </div>
      </div>
      <div className="job-summary-grid">
        <Rows
          rows={[
            ["경력", experience || "원문 확인"],
            ["학력", d.education],
            ["근무형태", job.employment],
            ["모집 인원", d.headcount],
          ]}
        />
        <Rows
          rows={[
            ["급여", d.salary],
            ["직급/직책", d.position],
            ["근무지역", job.location],
            ["근무방식", job.workplace],
          ]}
        />
      </div>
      {!!job.skills?.length && (
        <div className="job-summary-skills" aria-label="요구 기술">
          {job.skills.map((s) => (
            <span key={s}>{s}</span>
          ))}
        </div>
      )}
      <span className="sr-only" role="status">
        {message}
      </span>
    </header>
  );
}

// 남은 시간을 1초마다 갱신한다.
function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const left = Date.parse(until) - now;
  if (left <= 0) return <strong className="job-countdown">마감</strong>;
  const days = Math.floor(left / dayMs);
  const time = new Date(left % dayMs).toISOString().slice(11, 19);
  return (
    <strong className="job-countdown">
      {days}
      <small>일</small> {time}
    </strong>
  );
}

// 공고 내용 탭 아래쪽: 근무지 위치, 접수 기간과 방법, 기업 정보.
export function JobExtras({ job }: { job: PublicJob }) {
  const d = job.details ?? {};
  const c = d.company;
  const mapQuery = encodeURIComponent(d.address ?? job.location);
  const knownPlace = !!d.address || job.location !== unknownLocation;
  return (
    <div className="job-extras">
      {knownPlace && (
        <section aria-labelledby="job-place-title">
          <h3 id="job-place-title">근무지 위치</h3>
          <div className="job-box job-place">
            <p>
              <MapPin size={18} aria-hidden="true" />
              {d.address ?? job.location}
            </p>
            {d.station && (
              <p>
                <TrainFront size={18} aria-hidden="true" />
                {d.station}
              </p>
            )}
            <a
              className="job-box-link"
              href={`https://map.naver.com/p/search/${mapQuery}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              지도 보기<span className="sr-only"> (새 창)</span>
            </a>
          </div>
        </section>
      )}
      <section aria-labelledby="job-period-title">
        <h3 id="job-period-title">접수 기간, 방법</h3>
        <div className="job-box job-period">
          <div className="job-period-time">
            {job.closesAt ? (
              <>
                <span>남은 기간</span>
                <Countdown until={job.closesAt} />
                <dl>
                  {d.startsAt && (
                    <div>
                      <dt>시작일</dt>
                      <dd>{dateTime(d.startsAt)}</dd>
                    </div>
                  )}
                  <div>
                    <dt className="is-end">마감일</dt>
                    <dd className="is-end">{dateTime(job.closesAt)}</dd>
                  </div>
                </dl>
              </>
            ) : (
              <p>
                <CalendarClock size={18} aria-hidden="true" />
                마감일은 원문에서 확인해 주세요.
              </p>
            )}
          </div>
          <div className="job-period-method">
            <Rows
              rows={[
                ["지원 방법", d.applyMethod ?? "원문 확인"],
                ["제출 서류", d.documents?.join(", ")],
              ]}
            />
          </div>
        </div>
        <p className="job-note">
          <Info size={15} aria-hidden="true" />
          마감일은 기업 사정이나 조기 마감으로 바뀔 수 있어요.
        </p>
      </section>
      {c && (
        <section aria-labelledby="job-company-title">
          <h3 id="job-company-title">기업 정보</h3>
          <div className="job-box job-company">
            <div className="job-company-head">
              <span className="job-company-logo" aria-hidden="true">
                <Building2 size={22} />
              </span>
              <strong>{job.company}</strong>
            </div>
            <div className="job-summary-grid">
              <Rows
                rows={[
                  ["대표자", c.ceo],
                  ["업종", c.industry],
                  ["설립일", c.founded],
                  ["홈페이지", c.homepage],
                ]}
              />
              <Rows
                rows={[
                  ["기업 형태", c.type],
                  ["사원 수", c.employees],
                  ["매출액", c.revenue],
                  ["주소", c.address],
                ]}
              />
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
