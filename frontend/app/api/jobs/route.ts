import { experienceLabels, type ExperienceKind } from "@/lib/job-filters";
import { after } from "next/server";
import { collectedJobs, cachedJobFeed } from "@/lib/server/job-feed";
import { backendJob } from "@/lib/server/backend-jobs";
import { searchJobCatalog } from "@/lib/server/job-catalog";
import { dummyJobs } from "@/lib/dummy-jobs";
import type { PublicJob } from "@/types/public-job";
export const runtime = "nodejs";
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const offset = Number(params.get("offset") ?? 0),
    limit = Number(params.get("limit") ?? 4),
    role = params.get("role") ?? "all";
  const query = (params.get("q") ?? "").trim().toLowerCase().slice(0, 200);
  const jobId = params.get("id");
  const location = (params.get("location") || "")
    .trim()
    .toLowerCase()
    .slice(0, 100);
  const workplace = params.get("workplace") || "all";
  const sort = params.get("sort") || "newest";
  const experience = (params.get("experience") || "")
    .split(",")
    .filter(Boolean);
  if (
    !["all", "remote", "hybrid", "on-site", "unknown"].includes(workplace) ||
    !["newest", "closing", "company"].includes(sort) ||
    experience.some((value) => !Object.hasOwn(experienceLabels, value)) ||
    !Number.isSafeInteger(offset) ||
    offset < 0 ||
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > 24 ||
    !["all", "data", "backend"].includes(role)
  )
    return Response.json({ error: "잘못된 조회 조건입니다." }, { status: 400 });
  if (jobId?.startsWith("be:") && !/^be:[1-9]\d*$/.test(jobId))
    return Response.json({ error: "잘못된 공고 ID입니다." }, { status: 400 });
  try {
    // 예시 상세는 외부 수집·백엔드 목록 조회를 기다리지 않는다.
    if (jobId?.startsWith("dummy:")) {
      const job = dummyJobs.find((item) => item.id === jobId);
      return Response.json(
        {
          jobs: job ? [job] : [],
          total: job ? 1 : 0,
          nextOffset: null,
          checkedAt: new Date().toISOString(),
          unavailableSources: [],
        },
        { headers: { "Cache-Control": "no-store" } },
      );
    }
    if (jobId?.startsWith("be:")) {
      const id = Number(jobId.slice(3));
      if (!Number.isSafeInteger(id))
        return Response.json(
          { error: "잘못된 공고 ID입니다." },
          { status: 400 },
        );
      const job = await backendJob(id);
      return Response.json(
        {
          jobs: job ? [job] : [],
          total: job ? 1 : 0,
          nextOffset: null,
          checkedAt: new Date().toISOString(),
          unavailableSources: [],
        },
        { headers: { "Cache-Control": "no-store" } },
      );
    }
    const emptyFeed = {
      jobs: [] as PublicJob[],
      checkedAt: new Date().toISOString(),
    };
    const collected = jobId
      ? await collectedJobs().catch(() => emptyFeed)
      : (cachedJobFeed() ?? emptyFeed);
    if (!jobId)
      after(async () => {
        await collectedJobs().catch(() => undefined);
      });
    if (jobId) {
      const job = collected.jobs.find((item) => item.id === jobId);
      return Response.json(
        {
          jobs: job ? [job] : [],
          total: job ? 1 : 0,
          nextOffset: null,
          checkedAt: collected.checkedAt,
          unavailableSources: [],
        },
        { headers: { "Cache-Control": "no-store" } },
      );
    }
    const { profilePool } = await import("@/lib/server/posting-levels");
    const database = profilePool();
    if (!database) throw new Error("채용 공고 DB 연결 설정이 필요합니다.");
    const page = await searchJobCatalog(
      database,
      {
        query,
        role,
        location,
        workplace,
        sort,
        experience: experience as ExperienceKind[],
        offset,
        limit,
      },
      collected.jobs,
    );
    return Response.json(
      {
        ...page,
        checkedAt: new Date().toISOString(),
        unavailableSources: [],
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json(
      { error: "채용 공고를 불러오지 못했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}
