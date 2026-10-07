"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink } from "lucide-react";
import { openCareerSpace } from "@/lib/guest-session";
import type { Workspace } from "@/types/workspace";
import type { PublicJob } from "@/types/public-job";
import type { StudyTier } from "@/lib/study-prototype";
import { applicationKey, useStudies } from "./study-provider";

export function ApplicationConfirmation({
  job,
  tier,
}: {
  job: PublicJob;
  tier: StudyTier | null;
}) {
  const { state, ready, apply } = useStudies();
  const [checked, setChecked] = useState(false);
  const [applied, setApplied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (tier) return;
    let active = true;
    openCareerSpace()
      .then(async (response) => {
        if (!response.ok) throw new Error("지원 기록을 불러오지 못했어요.");
        const data: { workspace: Workspace } = await response.json();
        if (active)
          setApplied(
            data.workspace.applications.some(
              (a) => a.url === job.url && a.stage !== "지원 준비",
            ),
          );
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [job.url, tier]);
  const done = tier
    ? state.applied.includes(applicationKey(job.id, tier))
    : applied;
  async function confirm() {
    if (!checked || busy) return;
    if (tier) {
      apply(job.id, tier);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await openCareerSpace();
      if (!response.ok) throw new Error("저장 공간에 연결하지 못했어요.");
      const { workspace }: { workspace: Workspace } = await response.json();
      const existing = workspace.applications.find((a) => a.url === job.url);
      const applications = existing
        ? workspace.applications.map((a) =>
            a.id === existing.id && a.stage === "지원 준비"
              ? { ...a, stage: "지원 완료" }
              : a,
          )
        : [
            ...workspace.applications,
            {
              id: crypto.randomUUID(),
              company: job.company,
              title: job.title,
              url: job.url,
              stage: "지원 완료",
              date: new Date().toISOString().slice(0, 10),
              resumeId: "",
              snapshot: [],
              notes: "사용자가 직접 지원 완료를 확인함",
            },
          ];
      const saved = await fetch("/api/career", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "applications", applications }),
      });
      if (!saved.ok)
        throw new Error("지원 기록을 저장하지 못했어요. 다시 시도해 주세요.");
      setApplied(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="study-application">
      <div>
        <h3>{done ? "지원 완료로 기록했어요" : "이 공고에 지원하셨나요?"}</h3>
        <p>
          {tier
            ? "예시 지원 기록은 실제 지원 내역과 분리해 이 브라우저에 저장돼요."
            : "공고 원문에서 지원한 뒤 직접 확인해 주세요. 원문 열기만으로 지원 처리되지 않아요."}
        </p>
      </div>
      {done ? (
        <span className="study-confirmed">
          <CheckCircle2 size={17} />
          지원했어요 · {tier ? "예시" : "직접 확인"}
        </span>
      ) : (
        <div className="study-application-actions">
          {!tier && (
            <a href={job.url} target="_blank" rel="noopener noreferrer">
              공고 원문에서 지원
              <ExternalLink size={15} />
            </a>
          )}
          <label>
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            {tier
              ? "예시 공고에 지원한 상태로 체험할게요"
              : "이 공고에 지원을 완료했어요"}
          </label>
          <button
            className="study-primary"
            disabled={!checked || busy || !ready}
            onClick={() => void confirm()}
          >
            {busy ? "저장 중…" : "지원했어요"}
          </button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
