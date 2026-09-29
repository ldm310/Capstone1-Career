"use client";
import { GrowthHub } from "@/components/growth/growth-hub";
import { SourcesPanel } from "./panels/sources";
import { JobsPanel } from "./panels/jobs";
import { PreferencesPanel } from "./panels/preferences";
import { PlanPanel } from "./panels/plan";
import { SchedulePanel } from "./panels/schedule";
import { ApplicationsPanel } from "./panels/applications";
import { InterviewPanel } from "./panels/interview";
import { SharePanel } from "./panels/share";
import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { openCareerSpace } from "@/lib/guest-session";
import type { Workspace } from "@/types/workspace";
import type { PublicJob } from "@/types/public-job";
import { currentFindings, targetSkills, day } from "@/lib/workspace-selectors";
import {
  selectedSectionTab,
  type FeatureSection,
} from "@/lib/feature-sections";
const tabs = [
  ["overview", "성장 대시보드"],
  ["skills", "내 기술"],
  ["tasks", "단계별 과제"],
  ["ranking", "랭킹·공개 설정"],
  ["sources", "자료 추가"],
  ["jobs", "공고 비교·추천"],
  ["plan", "주간 계획"],
  ["schedule", "일정·알림"],
  ["applications", "지원·이력서"],
  ["interview", "면접 준비"],
  ["share", "포트폴리오 공유"],
];
export function CareerWorkspace({
  section,
}: { section?: FeatureSection } = {}) {
  const router = useRouter();
  const params = useSearchParams();
  const tab = section
    ? selectedSectionTab(section, params.get("tab"))
    : tabs.some(([key]) => key === params.get("tab"))
      ? params.get("tab")!
      : "overview";
  const [guest, setGuest] = useState(false);
  const [state, setState] = useState<Workspace | null>(null),
    [name, setName] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [error, setError] = useState(""),
    [jobs, setJobs] = useState<PublicJob[]>([]),
    [jobsError, setJobsError] = useState(""),
    [shares, setShares] = useState<string[]>([]),
    [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    openCareerSpace()
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        if (active) {
          setState(data.workspace);
          setName(data.user.name);
          setGuest(data.guest === true);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  async function request(url: string, body: unknown, method = "POST") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await fetch(url, {
        method,
        ...(body instanceof FormData
          ? { body }
          : {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "처리하지 못했습니다.");
      if (data.workspace) setState(data.workspace);
      setNotice(guest ? "게스트 공간에 저장했어요." : "서버에 저장했습니다.");
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "요청 실패");
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function save(action: string, patch: object) {
    const previous = state;
    if (action === "tasks" && state) setState({ ...state, ...patch });
    const result = await request("/api/career", { action, ...patch });
    if (!result && action === "tasks") setState(previous);
    return result;
  }
  const authenticated = !!state;
  useEffect(() => {
    if (tab !== "jobs" || !authenticated) return;
    let active = true;
    async function load() {
      try {
        const all: PublicJob[] = [];
        let offset: number | null = 0;
        while (offset !== null && offset < 300) {
          const res: Response = await fetch(
            `/api/jobs?limit=24&offset=${offset}&role=all`,
          );
          if (!res.ok)
            throw new Error(
              "공고를 불러오지 못했습니다. 페이지를 다시 열어주세요.",
            );
          const data: import("@/types/public-job").PublicJobsResponse =
            await res.json();
          all.push(...data.jobs);
          offset = data.nextOffset;
        }
        if (active) {
          setJobs(all);
          setJobsError("");
        }
      } catch (e) {
        if (active) setJobsError(String(e));
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [tab, authenticated]);
  useEffect(() => {
    if (tab !== "share" || !authenticated) return;
    fetch("/api/share")
      .then((r) => r.json())
      .then((d) =>
        setShares((d.shares || []).map((s: { token: string }) => s.token)),
      )
      .catch(() => setError("공유 링크를 불러오지 못했습니다."));
  }, [tab, authenticated]);
  if (loading) return <p role="status">커리어 공간을 여는 중…</p>;
  if (!state)
    return (
      <div className="career-panel">
        <h1>커리어 공간을 열지 못했어요</h1>
        <p role="alert">{error || "연결을 확인하고 다시 시도해 주세요."}</p>
        <button
          className="career-primary"
          onClick={() => window.location.reload()}
        >
          다시 시도하기
        </button>
        <Link href="/dashboard">샘플로 기능 둘러보기 →</Link>
      </div>
    );
  const findings = currentFindings(state),
    skills = [...new Set(findings.map((f) => f.skill))],
    targets = targetSkills[state.role] || targetSkills.ax;
  const gaps = targets.filter(
    (s) => !findings.some((f) => f.skill === s && f.type === "implementation"),
  );
  const next = gaps[0];
  const upcoming = state.events
    .filter((e) => e.date >= day() && e.date.slice(0, 10) <= day(7))
    .sort((a, b) => a.date.localeCompare(b.date));
  const latest = state.runs[0],
    previous =
      latest && state.runs.slice(1).find((r) => r.title === latest.title);
  const added = [
    ...new Map(
      (
        latest?.findings.filter(
          (f) => !previous?.findings.some((p) => p.skill === f.skill),
        ) || []
      ).map((f) => [f.skill, f]),
    ).values(),
  ];
  const removed = [
    ...new Map(
      (
        previous?.findings.filter(
          (f) => !latest?.findings.some((p) => p.skill === f.skill),
        ) || []
      ).map((f) => [f.skill, f]),
    ).values(),
  ];
  const jobSkills = state.job
    ? [
        ...new Set([
          ...state.job.required,
          ...state.job.preferred,
          ...state.job.unknown,
        ]),
      ]
    : [];
  const questions = (jobSkills.length ? jobSkills : targets)
    .slice(0, 6)
    .map((skill) => ({
      key: skill,
      text: `${skill}을 사용한 경험을 설명하고, 선택 이유와 한계·개선 방법을 이야기해 주세요.`,
      evidence: findings.find((f) => f.skill === skill),
    }));
  const panelProps = {
    state,
    findings,
    skills,
    gaps,
    next,
    upcoming,
    latest,
    previous,
    added,
    removed,
    jobs,
    busy,
    request,
    save,
    setNotice,
    params,
    jobsError,
    setError,
    targets,
    jobSkills,
    questions,
    shares,
    selected,
    setSelected,
    setShares,
  };
  return (
    <div className="career-workspace">
      {section ? (
        <details className="guest-information">
          <summary>
            {guest ? "로그인 없이 이용 중 · 게스트 공간" : `${name}님의 공간`} ·
            저장 안내
          </summary>
          <p>
            {guest
              ? "현재 브라우저에서 7일 동안 이어서 이용할 수 있어요. 쿠키를 지우면 새 공간이 열립니다. 자료는 현재 서버에 저장되며, 게스트 기록은 실제 랭킹에서 제외돼요."
              : "기존 계정의 자료를 사용하고 있어요."}
          </p>
          <Link href="/dashboard">샘플로 완료·포인트 체험하기 →</Link>
        </details>
      ) : (
        <header className="career-heading">
          <h1>{name}님의 커리어</h1>
        </header>
      )}
      <div aria-live="polite">
        {busy && (
          <p className="career-status">
            처리 중입니다. 분석에는 잠시 시간이 걸릴 수 있어요…
          </p>
        )}
        {notice && <p className="career-status">{notice}</p>}
        {error && (
          <p role="alert" className="career-error">
            {error}
          </p>
        )}
      </div>
      {[
        "overview",
        "summary",
        "history",
        "skills",
        "tasks",
        "ranking",
      ].includes(tab) && (
        <GrowthHub
          preparation={section === "preparation"}
          role={state.role}
          view={tab}
          findings={findings}
          targets={targets}
          onSources={() => router.push("/my-skills")}
        />
      )}
      {tab === "sources" && (
        <>
          <PreferencesPanel {...panelProps} />
          <SourcesPanel {...panelProps} />
          <Link className="career-primary" href="/my-skills?tab=skills">
            분석 결과·근거 확인하기 →
          </Link>
        </>
      )}
      {tab === "jobs" && <JobsPanel {...panelProps} />}
      {(tab === "plan" || tab === "jobs") && (
        <PreferencesPanel {...panelProps} />
      )}
      {tab === "plan" && (
        <>
          <GrowthHub view="plan" findings={findings} targets={targets} />
          <details>
            <summary>기존 준비 계획</summary>
            <PlanPanel {...panelProps} />
          </details>
        </>
      )}
      {tab === "schedule" && <SchedulePanel {...panelProps} />}
      {tab === "applications" && <ApplicationsPanel {...panelProps} />}
      {tab === "interview" && <InterviewPanel {...panelProps} />}
      {tab === "share" && <SharePanel {...panelProps} />}
    </div>
  );
}
