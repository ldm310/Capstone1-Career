"use client";
import { useEffect, useState } from "react";
import type { JobBenchmark } from "./job-benchmark";

export function useJobBenchmark(jobId: string) {
  const [result, setResult] = useState<{
    jobId: string;
    data?: JobBenchmark;
    error?: string;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/jobs/benchmark?jobId=${encodeURIComponent(jobId)}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("비교 자료를 불러오지 못했어요.");
        const data = (await response.json()) as JobBenchmark;
        if (
          data.jobId !== jobId ||
          !["SYNTHETIC", "UNAVAILABLE"].includes(data.source) ||
          !Array.isArray(data.applicants) ||
          !Array.isArray(data.passed) ||
          !Array.isArray(data.qualifications)
        )
          throw new Error("비교 자료를 확인하지 못했어요.");
        if (!controller.signal.aborted) setResult({ jobId, data });
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted)
          setResult({ jobId, error: error.message });
      });
    return () => controller.abort();
  }, [jobId, attempt]);
  const current = result?.jobId === jobId ? result : null;
  return { ...current, retry: () => setAttempt((value) => value + 1) };
}
