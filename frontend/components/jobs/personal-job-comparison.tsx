"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { signInUrl } from "@/lib/login-destination";
import { currentFindings } from "@/lib/workspace-selectors";
import {
  visibleSkillCategories as skillCategories,
  hasVisibleSkillCategory,
} from "@/lib/skill-categories";
import {
  connectJobEvidence,
  type PostingKeyword,
  type PersonalKeyword,
} from "@/lib/job-evidence";
import type { Workspace } from "@/types/workspace";
import type { SkillReview } from "@/types/growth";
import type { PostingLevels } from "@/types/posting-level";
import { SavedLevelRadar } from "./saved-level-radar";
import { RadarPoint } from "./radar-point";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

interface Result {
  jobId: string;
  viewer: "visitor" | "member";
  keywords: PostingKeyword[];
  example: boolean;
  sourceCount: number;
  rows: PersonalKeyword[];
  error?: string;
  keywordError?: string;
  saved?: PostingLevels;
  levelError?: string;
}

function EvidenceRadar({ rows }: { rows: PersonalKeyword[] }) {
  const hasLevels = rows.some(
    (row) => hasVisibleSkillCategory(row.categoryCodes) && row.assessed,
  );
  const axes = skillCategories.map((category) => {
    const items = rows.filter((row) =>
      row.categoryCodes.includes(category.code),
    );
    const scored = items.filter((row) => row.myLevel !== null);
    const linked = items.filter((row) => row.evidence.length).length;
    return {
      ...category,
      total: items.length,
      linked,
      value: hasLevels
        ? scored.length
          ? Math.round(
              scored.reduce((sum, row) => sum + row.myLevel!, 0) /
                scored.length,
            )
          : null
        : items.length
          ? Math.round((linked / items.length) * 100)
          : null,
    };
  });
  const point = (index: number, value: number) => {
    const angle = (index / axes.length) * 2 * Math.PI - Math.PI / 2;
    return {
      x: 230 + Math.cos(angle) * value,
      y: 175 + Math.sin(angle) * value,
    };
  };
  const polygon = (values: (number | null)[]) =>
    values
      .map((value, index) => {
        const p = point(index, (value ?? 0) * 1.02);
        return `${p.x},${p.y}`;
      })
      .join(" ");
  const label = hasLevels
    ? "평가 완료 키워드의 카테고리별 LV 평균"
    : "공고 요건 중 내 자료의 근거 후보가 연결된 비율";
  return (
    <section
      className="personal-radar-card"
      aria-labelledby="personal-radar-title"
    >
      <header>
        <h4 id="personal-radar-title">
          {hasLevels ? "공고별 내 역량" : "공고별 근거 연결 현황"}
        </h4>
        <p>{label}</p>
      </header>
      <svg
        viewBox="0 0 460 350"
        role="group"
        aria-label={`${label}. ${axes.map((axis) => `${axis.name}: ${axis.value === null ? "평가 자료 없음" : axis.value}${hasLevels ? "" : `, 후보 ${axis.linked}/${axis.total}개`}`).join(". ")}`}
      >
        <title>{label}</title>
        {[20, 40, 60, 80, 100].map((tick) => (
          <polygon
            key={tick}
            points={polygon(axes.map(() => tick))}
            fill="none"
            stroke="#dce6ee"
          />
        ))}
        {axes.map((axis, index) => {
          const edge = point(index, 102),
            text = point(index, 137);
          return (
            <g key={axis.code}>
              <line
                x1="230"
                y1="175"
                x2={edge.x}
                y2={edge.y}
                stroke="#e6edf2"
              />
              <text
                x={text.x}
                y={text.y}
                textAnchor={
                  Math.abs(text.x - 230) < 8
                    ? "middle"
                    : text.x > 230
                      ? "start"
                      : "end"
                }
                fontSize="11"
                fill="#4a6072"
              >
                {axis.label.map((line, i) => (
                  <tspan key={line} x={text.x} dy={i ? 14 : 0}>
                    {line.replaceAll("·", ", ")}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
        {hasLevels ? (
          <polyline
            points={axes
              .flatMap((axis, index) => {
                if (axis.value === null) return [];
                const p = point(index, axis.value * 1.02);
                return [`${p.x},${p.y}`];
              })
              .join(" ")}
            fill="none"
            stroke="#315e7e"
            strokeWidth="2"
          />
        ) : (
          <polygon
            points={polygon(axes.map((axis) => axis.value))}
            fill="#315e7e"
            fillOpacity=".15"
            stroke="#315e7e"
            strokeWidth="2"
          />
        )}
        {axes.map((axis, index) => {
          if (axis.value === null) return null;
          const p = point(index, axis.value * 1.02);
          return (
            <RadarPoint
              key={axis.code}
              x={p.x}
              y={p.y}
              color="#315e7e"
              category={axis.name.replaceAll("·", ", ")}
              series={hasLevels ? "내" : "근거 후보 연결률"}
              unit={hasLevels ? "LV" : "%"}
              score={axis.value}
              viewWidth={460}
            />
          );
        })}
      </svg>
      <ul className="personal-comparison-notes">
        {hasLevels ? (
          <li>평가가 완료된 역량 문장, 키워드만 평균에 포함합니다.</li>
        ) : (
          <>
            <li>근거 후보 연결률은 LV, 합격 점수가 아닙니다.</li>
            <li>연결된 내용은 항목별로 확인할 수 있습니다.</li>
          </>
        )}
        <li>공고에 해당 요건이 없는 카테고리는 평가하지 않습니다.</li>
      </ul>
    </section>
  );
}

export function PersonalJobComparison({ jobId }: { jobId: string }) {
  const pathname = usePathname(),
    params = useSearchParams();
  const loginUrl = signInUrl(
    pathname + (params.size ? "?" + params.toString() : ""),
  );
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const refresh = () => {
      setResult(null);
      setAttempt((value) => value + 1);
    };
    window.addEventListener("career:account", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("career:account", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const read = async (url: string) => {
      const response = await fetch(url, {
        signal: controller.signal,
        cache: "no-store",
      });
      return { response, data: await response.json() };
    };
    (async () => {
      const [keywordResult, accountResult] = await Promise.allSettled([
        read(`/api/jobs/keywords?jobId=${encodeURIComponent(jobId)}`),
        read("/api/account"),
      ]);
      if (controller.signal.aborted) return;
      const keywordData =
        keywordResult.status === "fulfilled" ? keywordResult.value : null;
      const account =
        accountResult.status === "fulfilled" ? accountResult.value : null;
      const keywords =
        keywordData?.response.ok && Array.isArray(keywordData.data.keywords)
          ? (keywordData.data.keywords as PostingKeyword[])
          : [];
      const current: Result = {
        jobId,
        viewer: "visitor",
        keywords,
        rows: [],
        sourceCount: 0,
        example: keywordData?.data.source === "EXAMPLE",
        keywordError: !keywordData?.response.ok
          ? "공고의 역량 키워드를 불러오지 못했습니다."
          : undefined,
      };
      if (!account?.response.ok) {
        setResult({ ...current, error: "로그인 상태를 확인하지 못했습니다." });
        return;
      }
      if (!account.data.user || account.data.guest !== false) {
        setResult(current);
        return;
      }
      current.viewer = "member";
      if (keywordData?.data.version) {
        try {
          const saved = await read(
            `/api/jobs/my-levels?jobId=${encodeURIComponent(jobId)}&version=${encodeURIComponent(keywordData.data.version)}`,
          );
          if (saved.response.ok) {
            const data = saved.data as PostingLevels;
            const matching = data.levels.filter((row) =>
              keywords.some(
                (keyword) =>
                  keyword.id === row.keywordId &&
                  keyword.text === row.text &&
                  [...keyword.categoryCodes].sort().join() ===
                    [...row.categoryCodes].sort().join(),
              ),
            );
            if (matching.length) current.saved = { ...data, levels: matching };
          } else if (saved.response.status !== 503)
            current.levelError = "저장된 LV를 불러오지 못했습니다.";
        } catch {
          current.levelError = "저장된 LV를 불러오지 못했습니다.";
        }
      }
      if (controller.signal.aborted) return;
      const [career, growth] = await Promise.allSettled([
        read("/api/career"),
        read("/api/growth"),
      ]);
      if (controller.signal.aborted) return;
      if (
        career.status !== "fulfilled" ||
        !career.value.response.ok ||
        !career.value.data.workspace
      ) {
        setResult({ ...current, error: "내 분석 자료를 불러오지 못했습니다." });
        return;
      }
      const workspace = career.value.data.workspace as Workspace;
      const reviews: SkillReview[] =
        growth.status === "fulfilled" && growth.value.response.ok
          ? (growth.value.data.growth?.reviews ?? [])
          : [];
      current.sourceCount =
        current.saved?.sources.length || workspace.runs.length;
      current.rows = connectJobEvidence(
        keywords,
        currentFindings(workspace),
        reviews,
      );
      if (current.saved)
        current.rows = current.rows.map((row) => {
          const saved = current.saved!.levels.find(
            (level) => level.keywordId === row.id,
          );
          return saved ? { ...row, myLevel: saved.score, assessed: true } : row;
        });
      setResult(current);
    })().catch(() => {
      if (!controller.signal.aborted)
        setResult({
          jobId,
          viewer: "visitor",
          keywords: [],
          rows: [],
          example: false,
          sourceCount: 0,
          error: "역량 비교 정보를 불러오지 못했습니다.",
        });
    });
    return () => controller.abort();
  }, [jobId, attempt]);
  const current = result?.jobId === jobId ? result : null;
  const retry = () => setAttempt((value) => value + 1);
  return (
    <section
      id="job-personal-comparison"
      className="personal-job-comparison"
      aria-label="역량 분석"
    >
      {!current ? (
        <LoadingSpinner inline />
      ) : (
        <>
          {current.error ? (
            <div className="personal-comparison-message" role="alert">
              <p>{current.error}</p>
              <button onClick={retry}>다시 확인</button>
            </div>
          ) : current.viewer === "visitor" ? (
            <div className="personal-comparison-message">
              <h3>개인 역량 분석</h3>
              <p>
                로그인 후 GitHub, PDF 자료로 공고별 역량을 확인할 수 있습니다.
              </p>
              <Link href={loginUrl}>로그인, 회원가입</Link>
            </div>
          ) : !current.sourceCount ? (
            <div className="personal-comparison-message">
              <h3>분석 자료 미등록</h3>
              <p>GitHub 링크 또는 PDF 이력서를 등록해 주세요.</p>
              <Link href="/analysis">자료 등록, 분석</Link>
            </div>
          ) : (
            <>
              {current.saved ? (
                <SavedLevelRadar levels={current.saved.levels} />
              ) : (
                !!current.rows.length && <EvidenceRadar rows={current.rows} />
              )}
              <div className="personal-comparison-footer">
                <Link href="/analysis">자료 추가</Link>
              </div>
            </>
          )}
          {current.keywordError && (
            <p className="personal-comparison-note" role="status">
              {current.keywordError} <button onClick={retry}>다시 확인</button>
            </p>
          )}
          {current.levelError && (
            <p className="personal-comparison-note" role="status">
              {current.levelError} <button onClick={retry}>다시 확인</button>
            </p>
          )}
          {!current.keywordError &&
            current.viewer === "member" &&
            current.sourceCount > 0 &&
            !current.keywords.length && (
              <p className="personal-comparison-note">
                이 공고의 분류된 역량 정보가 아직 없습니다.
              </p>
            )}
        </>
      )}
    </section>
  );
}
