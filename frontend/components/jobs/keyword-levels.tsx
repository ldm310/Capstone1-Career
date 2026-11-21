"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { skillCategories } from "@/lib/skill-categories";

interface Result {
  jobId: string;
  source?: string;
  keywords?: {
    id: string;
    text: string;
    categoryCodes: string[];
    level: number | null;
  }[];
  error?: string;
}
export function KeywordLevels({ jobId }: { jobId: string }) {
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/jobs/keywords?jobId=${encodeURIComponent(jobId)}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok || !Array.isArray(data.keywords))
          throw new Error(data.error || "키워드를 불러오지 못했어요.");
        if (!controller.signal.aborted) setResult({ ...data, jobId });
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted)
          setResult({ jobId, error: error.message });
      });
    return () => controller.abort();
  }, [jobId, attempt]);
  const current = result?.jobId === jobId ? result : null;
  return (
    <section className="job-keyword-levels" aria-labelledby="job-keyword-title">
      <header>
        <h3 id="job-keyword-title">이 공고에서 확인할 나의 역량</h3>
        <p>임베딩으로 분류·검토한 역량 문장과 키워드를 기준으로 확인해요.</p>
      </header>
      {!current ? (
        <p role="status">공고의 키워드를 불러오는 중이에요.</p>
      ) : current.error ? (
        <div role="alert">
          <p>{current.error}</p>
          <button onClick={() => setAttempt((value) => value + 1)}>
            키워드 다시 불러오기
          </button>
        </div>
      ) : current.keywords?.length ? (
        <>
          {current.source === "EXAMPLE" && (
            <p className="job-keyword-note">
              저장된 분류 문장으로 구성한 화면 예시예요. 이 가상 공고의 실제
              요건은 아니에요.
            </p>
          )}
          <ul>
            {current.keywords.map((keyword) => (
              <li key={keyword.id}>
                <div>
                  <strong>{keyword.text}</strong>
                  <p>
                    {keyword.categoryCodes
                      .map(
                        (code) =>
                          skillCategories.find(
                            (category) => category.code === code,
                          )?.name,
                      )
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <span className="job-keyword-lv">
                  LV <b>{keyword.level ?? "—"}</b>
                  <small>
                    {keyword.level === null ? "산정 전" : "나의 역량"}
                  </small>
                </span>
              </li>
            ))}
          </ul>
          <p className="job-keyword-note">
            키워드 분류는 반영했어요. LV 산정 결과가 연결되면 각 항목에
            표시해요.
          </p>
        </>
      ) : (
        <p className="job-keyword-note">
          이 공고에는 검토가 완료된 역량 키워드가 아직 없어요.
        </p>
      )}
      <Link href="/analysis">내 자료 추가·분석하기 →</Link>
    </section>
  );
}
