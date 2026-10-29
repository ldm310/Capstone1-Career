"use client";
import { GrowthHub } from "@/components/growth/growth-hub";
import { SourcesPanel } from "./panels/sources";
import { PreferencesPanel } from "./panels/preferences";
import { SharePanel } from "./panels/share";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { openCareerSpace } from "@/lib/guest-session";
import type { Workspace } from "@/types/workspace";
import { currentFindings, targetSkills } from "@/lib/workspace-selectors";
import {
  selectedSectionTab,
  type FeatureSection,
} from "@/lib/feature-sections";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
export function CareerWorkspace({ section }: { section: FeatureSection }) {
  const params = useSearchParams();
  const tab = selectedSectionTab(section, params.get("tab"));
  const [guest, setGuest] = useState(false);
  const [state, setState] = useState<Workspace | null>(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [error, setError] = useState(""),
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
      if (!res.ok) throw new Error(data.error || "처리하지 못했어요.");
      if (data.workspace) setState(data.workspace);
      setNotice("저장했어요.");
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
    if (tab !== "share" || !authenticated) return;
    fetch("/api/share")
      .then((r) => r.json())
      .then((d) =>
        setShares((d.shares || []).map((s: { token: string }) => s.token)),
      )
      .catch(() => setError("공유 링크를 불러오지 못했어요."));
  }, [tab, authenticated]);
  if (loading) return <LoadingSpinner />;
  if (!state)
    return (
      <div className="career-panel">
        <h1>열지 못했어요</h1>
        <p role="alert">{error || "연결을 확인해 주세요."}</p>
        <button
          className="career-primary"
          onClick={() => window.location.reload()}
        >
          다시 시도
        </button>
      </div>
    );
  const findings = currentFindings(state),
    skills = [...new Set(findings.map((f) => f.skill))],
    targets = targetSkills[state.role] || targetSkills.data;
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
      text: `${skill}을 사용한 경험과 선택 이유를 설명해 주세요.`,
      evidence: findings.find((f) => f.skill === skill),
    }));
  const panelProps = {
    state,
    findings,
    skills,
    busy,
    request,
    save,
    setNotice,
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
      {guest && <p className="guest-information">게스트 공간, 7일 보관</p>}
      <div aria-live="polite">
        {busy && <p className="career-status">처리 중…</p>}
        {notice && <p className="career-status">{notice}</p>}
        {error && (
          <p role="alert" className="career-error">
            {error}
          </p>
        )}
      </div>
      {["skills", "next"].includes(tab) && (
        <GrowthHub
          preparation={tab === "next"}
          role={state.role}
          findings={findings}
          targets={targets}
        />
      )}
      {tab === "sources" && (
        <>
          <PreferencesPanel {...panelProps} />
          <SourcesPanel {...panelProps} />
          <Link className="career-primary" href="/my-skills">
            분석 결과 보기 →
          </Link>
        </>
      )}
      {tab === "share" && <SharePanel {...panelProps} />}
    </div>
  );
}
