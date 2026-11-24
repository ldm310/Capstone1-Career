"use client";
import { useEffect, useState } from "react";
import { openCareerSpace } from "@/lib/guest-session";
import type { PublicJob } from "@/types/public-job";

export type SavedJob = PublicJob & { savedAt: string };
export type SaveResult = { ok: boolean; message: string };

// 저장한 공고는 계정(게스트 포함)별로 서버에 보관한다. 여러 화면이 같은 목록을 함께 쓴다.
let cache: { jobs: SavedJob[] | null; error: string; loading: boolean } = {
  jobs: null,
  error: "",
  loading: false,
};
let loading: Promise<void> | null = null;
const listeners = new Set<(state: typeof cache) => void>();
function publish(patch: Partial<typeof cache>) {
  cache = { ...cache, ...patch };
  listeners.forEach((l) => l(cache));
}
async function request(init?: RequestInit) {
  const r = await fetch("/api/saved-jobs", init);
  const d = await r.json();
  if (r.status === 401 && !init) {
    publish({ jobs: [], error: "" });
    return;
  }
  if (!r.ok) throw new Error(d.error || "저장한 공고를 불러오지 못했어요.");
  publish({ jobs: d.jobs, error: "" });
}
function load() {
  if (loading) return loading;
  publish({ loading: true, error: "" });
  loading = request()
    .catch((error) =>
      publish({
        error:
          error instanceof Error
            ? error.message
            : "저장한 공고를 불러오지 못했어요.",
      }),
    )
    .finally(() => {
      loading = null;
      publish({ loading: false });
    });
  return loading;
}
// 목록에 넣을 값만 남긴다. 본문, 상세 정보는 상세 화면에서 다시 불러온다.
function snapshot(job: PublicJob) {
  const { id, company, title, category, location, employment, workplace } = job;
  return {
    id,
    company,
    title,
    category,
    location,
    employment,
    workplace,
    postedAt: job.postedAt,
    closesAt: job.closesAt ?? null,
    url: job.url,
    dummy: job.dummy,
    skills: job.skills,
    experience: job.experience,
  };
}

export function useSavedJobs() {
  const [state, setState] = useState(cache);
  useEffect(() => {
    listeners.add(setState);
    // 로그인, 로그아웃으로 계정이 바뀌었을 수 있으니 화면에 들어올 때마다 다시 확인한다.
    void load();
    return () => {
      listeners.delete(setState);
    };
  }, []);
  const isSaved = (id: string) => !!state.jobs?.some((j) => j.id === id);
  // 저장, 저장 취소를 바꾼다. 실패하면 메시지를 돌려준다.
  async function toggle(job: PublicJob): Promise<SaveResult> {
    const saved = isSaved(job.id);
    try {
      await openCareerSpace();
      await request({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          saved
            ? { action: "remove", id: job.id }
            : { action: "save", job: snapshot(job) },
        ),
      });
      return {
        ok: true,
        message: saved ? "저장을 취소했어요." : "저장했어요.",
      };
    } catch (e) {
      return {
        ok: false,
        message: e instanceof Error ? e.message : "저장하지 못했어요.",
      };
    }
  }
  return { ...state, retry: load, isSaved, toggle };
}
