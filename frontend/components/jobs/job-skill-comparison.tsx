"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, CircleHelp, FileText } from "lucide-react";
import { openCareerSpace } from "@/lib/guest-session";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { currentFindings } from "@/lib/workspace-selectors";
import type { Workspace } from "@/types/workspace";
import type { PublicJob } from "@/types/public-job";
import { OriginalLink } from "@/components/jobs/original-link";

// 실제 공고 본문을 분석해 필수, 우대 기술별로 내 근거가 있는지 보여준다.
export function JobSkillComparison({ job }: { job: PublicJob }) {
  const [state, setState] = useState<Workspace | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    openCareerSpace()
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw Error(d.error);
        if (active) setState(d.workspace);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function analyze() {
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "job",
          url: job.url,
          company: job.company,
          title: job.title,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error || "분석하지 못했어요.");
      setState(d.workspace);
    } catch (e) {
      setError(e instanceof Error ? e.message : "분석하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }
  const analysis = state?.job?.url === job.url ? state.job : null;
  // 탭을 열면 버튼 없이 바로 비교한다. 실패하면 다시 시도 버튼을 보여준다.
  const started = useRef(false);
  useEffect(() => {
    if (!state || analysis || started.current) return;
    started.current = true;
    void analyze();
    // analyze depends on job only; run once per mounted job.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, analysis]);
  const findings = state ? currentFindings(state) : [];
  const evidence = (skill: string) =>
    findings.some((f) => f.skill === skill && f.type === "implementation")
      ? "code"
      : findings.some((f) => f.skill === skill)
        ? "document"
        : "none";
  return (
    <section className="study-requirements">
      <h3>내 자료와 비교</h3>
      {error && <p role="alert">{error}</p>}
      {!analysis ? (
        error ? (
          <div className="job-compare-start">
            <p>비교하지 못했어요.</p>
            <button
              className="study-primary"
              disabled={busy}
              onClick={() => void analyze()}
            >
              다시 시도
            </button>
          </div>
        ) : (
          <LoadingSpinner inline />
        )
      ) : (
        <>
          {(
            [
              ["필수", analysis.required],
              ["우대", analysis.preferred],
              ["분류 미확인", analysis.unknown],
            ] as const
          ).map(([label, list]) =>
            list.length ? (
              <div key={label} className="job-compare-group">
                <h4>{label}</h4>
                {list.map((skill) => {
                  const kind = evidence(skill);
                  const Icon =
                    kind === "code"
                      ? CheckCircle2
                      : kind === "document"
                        ? FileText
                        : CircleHelp;
                  return (
                    <div className="study-requirement-row" key={skill}>
                      <Icon size={19} />
                      <div>
                        <strong>{skill}</strong>
                      </div>
                      <span
                        className={
                          kind === "none" ? "study-negative" : "study-positive"
                        }
                      >
                        {kind === "code"
                          ? "코드 근거"
                          : kind === "document"
                            ? "문서 근거"
                            : "근거 없음"}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : null,
          )}
          {!findings.length && (
            <p className="study-muted">
              자료가 없어요. <Link href="/my-data">자료 추가 →</Link>
            </p>
          )}
          <OriginalLink
            job={job}
            className="job-compare-source"
            label="분석한 공고 원문 보기"
          />
        </>
      )}
    </section>
  );
}
