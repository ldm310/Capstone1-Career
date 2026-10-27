"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BriefcaseBusiness,
  CircleHelp,
  Code2,
  FolderOpen,
} from "lucide-react";
import {
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from "recharts";
import { useReducedMotion } from "motion/react";
import {
  SkyBackground,
  SkyPlayback,
} from "@/components/landing/sky-background";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { openCareerSpace } from "@/lib/guest-session";
import { currentFindings, targetSkills } from "@/lib/workspace-selectors";
import { mergeReviews } from "@/lib/growth/model";
import { experienceLabels, jobExperience } from "@/lib/job-filters";
import { roleLabels } from "@/lib/korean";
import { emptyGrowth, type GrowthState } from "@/types/growth";
import type { Workspace } from "@/types/workspace";
import type { PublicJob } from "@/types/public-job";

const percent = (part: number, whole: number) =>
  whole ? Math.round((part / whole) * 100) : 0;

// 홈 대시보드: 내 자료, 역량 요약과 내 기술에 맞는 추천 공고를 한 화면에 보여준다.
export function HomeDashboard() {
  const reduced = useReducedMotion();
  const [name, setName] = useState("");
  const [guest, setGuest] = useState(true);
  const [state, setState] = useState<Workspace | null>(null);
  const [growth, setGrowth] = useState<GrowthState>(emptyGrowth);
  const [jobs, setJobs] = useState<PublicJob[] | null>(null);
  const [jobTotal, setJobTotal] = useState(0);
  const [now] = useState(() => Date.now());
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const r = await openCareerSpace();
        const d = await r.json();
        if (!r.ok || !active) return;
        setName(d.user?.name || "");
        setGuest(d.guest !== false);
        setState(d.workspace);
        const [g, j] = await Promise.all([
          fetch("/api/growth").then((x) => x.json()),
          fetch("/api/jobs?limit=24&role=all").then((x) => x.json()),
        ]);
        if (!active) return;
        if (g.growth) setGrowth(g.growth);
        setJobs(j.jobs || []);
        setJobTotal(j.total || 0);
      } catch {
        if (active) setJobs([]);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const findings = state ? currentFindings(state) : [];
  const mySkills = new Set(findings.map((f) => f.skill));
  const reviews = mergeReviews(growth, findings).reviews.filter(
    (r) => r.status !== "excluded",
  );
  const targets = targetSkills[state?.role || "data"] || targetSkills.data;
  const has = (s: string) => findings.some((f) => f.skill === s);
  const coded = (s: string) =>
    findings.some((f) => f.skill === s && f.type === "implementation");
  const levels: number[] = reviews.map((r) => r.level || 0);
  const submitted = growth.tasks.filter((t) => t.submissions.length).length;
  const answered = Object.values(state?.answers || {}).filter(Boolean).length;
  // 자료에서 계산한 추정치(0~100). 기업 평가나 합격 예측이 아니다.
  const radar = [
    ["기술 충족도", percent(targets.filter(has).length, targets.length)],
    ["직무 연관성", percent(targets.filter(coded).length, targets.length)],
    [
      "구현 완성도",
      percent(levels.filter((l) => l >= 2).length, levels.length),
    ],
    [
      "활용 깊이",
      percent(
        levels.reduce((a, b) => a + b, 0),
        levels.length * 3,
      ),
    ],
    [
      "문제 해결",
      percent(levels.filter((l) => l === 3).length * 2, levels.length),
    ],
    [
      "성과 명확성",
      Math.min(
        100,
        percent(submitted, growth.tasks.length) / 2 + percent(answered, 6) / 2,
      ),
    ],
  ].map(([axis, value]) => ({ axis, value: Math.min(100, Number(value)) }));

  const recommended = (jobs || [])
    .map((job) => {
      const skills = job.skills || [];
      return {
        job,
        linked: skills.filter((s) => mySkills.has(s)).length,
        missing: skills.filter((s) => !mySkills.has(s)).length,
      };
    })
    .sort(
      (a, b) =>
        Number(b.job.category === state?.role) -
          Number(a.job.category === state?.role) ||
        b.linked - a.linked ||
        a.missing - b.missing,
    )
    .slice(0, 3);
  const pending = reviews.filter((r) => r.status === "pending").length;
  const stats = [
    ["프로젝트", state?.runs.length ?? 0, FolderOpen, "/my-data"],
    ["확인 기술", reviews.filter((r) => r.level).length, Code2, "/my-skills"],
    ["비교 공고", jobTotal, BriefcaseBusiness, "/jobs"],
    ["확인 필요", pending, CircleHelp, "/my-skills"],
  ] as const;

  return (
    <>
      <section className="sky-hero career-home-hero home-greeting">
        <SkyBackground className="home-sky-photo" />
        <div className="home-width home-greeting-copy">
          <span className="sky-eyebrow">
            {new Date(now).toLocaleDateString("ko-KR", {
              month: "long",
              day: "numeric",
              weekday: "long",
            })}
          </span>
          <h1 tabIndex={-1}>
            {!guest && name ? `${name}님의 Career` : "나의 Career"}
          </h1>
          <p>
            {findings.length
              ? "프로젝트 근거로 지금 준비 상태를 확인해요."
              : "자료를 추가하면 내 역량과 추천 공고가 채워져요."}
          </p>
        </div>
        <SkyPlayback />
      </section>
      <div className="home-width home-dashboard">
        <ul className="home-stats">
          {stats.map(([label, value, Icon, href]) => (
            <li key={label}>
              <Link href={href}>
                <span className="home-stat-icon" aria-hidden="true">
                  <Icon size={20} />
                </span>
                <span>
                  <small>{label}</small>
                  <strong>
                    {state ? value : "-"}
                    <em>개</em>
                  </strong>
                </span>
              </Link>
            </li>
          ))}
        </ul>
        <div className="home-panels">
          <section className="home-panel" aria-labelledby="home-skill-title">
            <header>
              <div>
                <span className="home-panel-eyebrow">MY STAT</span>
                <h2 id="home-skill-title">내 역량</h2>
                <p>프로젝트에서 확인한 역량 범위예요.</p>
              </div>
              <Link href="/my-skills">
                전체 보기 <ArrowRight size={16} />
              </Link>
            </header>
            {!state ? (
              <LoadingSpinner inline />
            ) : findings.length ? (
              <div
                className="home-radar"
                role="img"
                aria-label={radar.map((r) => `${r.axis} ${r.value}`).join(", ")}
              >
                <ResponsiveContainer width="100%" height={300} minWidth={0}>
                  <RadarChart data={radar} outerRadius="68%">
                    <PolarGrid gridType="polygon" stroke="#e3e8ee" />
                    <PolarAngleAxis
                      dataKey="axis"
                      tick={{ fontSize: 12, fill: "#4b5b68" }}
                    />
                    <PolarRadiusAxis
                      domain={[0, 100]}
                      tick={false}
                      axisLine={false}
                    />
                    <Radar
                      dataKey="value"
                      name="나"
                      stroke="#2f6fb3"
                      strokeWidth={2.5}
                      fill="#5a9be0"
                      fillOpacity={0.2}
                      isAnimationActive={!reduced}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="home-empty">
                <p>아직 자료가 없어요.</p>
                <Link className="cta" href="/my-data">
                  자료 추가 <ArrowRight size={16} />
                </Link>
              </div>
            )}
          </section>
          <section
            className="home-panel"
            id="market-preview"
            aria-labelledby="home-jobs-title"
          >
            <header>
              <div>
                <span className="home-panel-eyebrow">MATCHED JOBS</span>
                <h2 id="home-jobs-title">추천 공고</h2>
                <p>내 프로젝트 경험과 연결되는 공고예요.</p>
              </div>
              <Link href="/jobs">
                전체 보기 <ArrowRight size={16} />
              </Link>
            </header>
            {!jobs ? (
              <LoadingSpinner inline />
            ) : !recommended.length ? (
              <p className="home-empty">조건에 맞는 공고가 없어요.</p>
            ) : (
              <ul className="home-jobs">
                {recommended.map(({ job, linked, missing }) => {
                  const days = job.closesAt
                    ? Math.ceil((Date.parse(job.closesAt) - now) / 86400000)
                    : null;
                  const kind = jobExperience(job)[0];
                  return (
                    <li key={job.id}>
                      <span className="home-job-mark" aria-hidden="true">
                        {job.company.slice(0, 1)}
                      </span>
                      <div className="home-job-main">
                        <small>
                          {job.company}
                          {kind ? `, ${experienceLabels[kind]}` : ""}
                        </small>
                        <h3>
                          <Link
                            href={`/jobs?job=${encodeURIComponent(job.id)}`}
                          >
                            {job.title}
                          </Link>
                        </h3>
                        <p>
                          {job.location}, {job.employment}
                          {job.closesAt &&
                            `, 마감 ${new Date(job.closesAt).toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" })}`}
                        </p>
                        {!!job.skills?.length && (
                          <div className="home-job-tags">
                            {job.skills.slice(0, 4).map((s) => (
                              <span
                                key={s}
                                className={mySkills.has(s) ? "is-mine" : ""}
                              >
                                {s}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="home-job-side">
                        {days !== null && days >= 0 && (
                          <b className="home-job-dday">D-{days}</b>
                        )}
                        <div className="home-job-counts">
                          <span>
                            <strong>{linked}</strong>
                            <small>연결 근거</small>
                          </span>
                          <span className="is-need">
                            <strong>{missing}</strong>
                            <small>확인 필요</small>
                          </span>
                        </div>
                        <Link
                          className="home-job-more"
                          href={`/jobs?job=${encodeURIComponent(job.id)}&view=compare`}
                        >
                          자세히 <ArrowRight size={15} />
                        </Link>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            {state && (
              <p className="home-panel-note">
                {roleLabels[state.role as keyof typeof roleLabels]} 직무 우선
              </p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
