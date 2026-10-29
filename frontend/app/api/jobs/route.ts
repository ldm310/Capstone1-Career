import {
  workplaceKey,
  experienceLabels,
  jobExperience,
  sortPublicJobs,
  type ExperienceKind,
} from "@/lib/job-filters";
import { collectedJobs } from "@/lib/server/job-feed";
import { backendJobs } from "@/lib/server/backend-jobs";
import { dummyJobs } from "@/lib/dummy-jobs";
import type { PublicJob } from "@/types/public-job";
const minimumJobs = 6;
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
    !["all", "remote", "hybrid", "on-site"].includes(workplace) ||
    !["newest", "closing", "company"].includes(sort) ||
    experience.some((value) => !Object.hasOwn(experienceLabels, value)) ||
    !Number.isInteger(offset) ||
    offset < 0 ||
    offset > 10000 ||
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > 24 ||
    !["all", "data", "backend"].includes(role)
  )
    return Response.json({ error: "잘못된 조회 조건입니다." }, { status: 400 });
  try {
    // 수집에 실패해도 더미 공고로 목록을 채운다. 실패 안내는 화면에 띄우지 않는다.
    // 백엔드 공고(BACKEND_URL)가 있으면 먼저 보여준다.
    const [collected, fromBackend] = await Promise.all([
      collectedJobs().catch(() => ({
        jobs: [] as PublicJob[],
        checkedAt: new Date().toISOString(),
      })),
      backendJobs(),
    ]);
    const feed = {
      ...collected,
      jobs: [...fromBackend, ...collected.jobs],
    };
    const matches = (job: PublicJob) =>
      (!jobId || job.id === jobId) &&
      (role === "all" || job.category === role) &&
      (!location || job.location.toLowerCase().includes(location)) &&
      (workplace === "all" || workplaceKey(job.workplace) === workplace) &&
      (!experience.length ||
        experience.some((value) =>
          jobExperience(job).includes(value as ExperienceKind),
        )) &&
      `${job.company} ${job.title} ${(job.skills || []).join(" ")}`
        .toLowerCase()
        .includes(query);
    // 조건에 맞는 실제 공고가 최소 개수보다 적으면 같은 조건의 더미 공고로 채운다.
    // 상세 조회는 모든 더미에서 찾는다.
    const real = feed.jobs.filter(matches),
      dummies = dummyJobs.filter(matches);
    const filtered = jobId
      ? [...real, ...dummies]
      : [...real, ...dummies.slice(0, Math.max(0, minimumJobs - real.length))];
    const sorted = sortPublicJobs(filtered, sort);
    return Response.json(
      {
        ...feed,
        unavailableSources: [],
        jobs: sorted.slice(offset, offset + limit),
        total: filtered.length,
        nextOffset: offset + limit < filtered.length ? offset + limit : null,
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json(
      { error: "채용공고를 불러오지 못했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}
