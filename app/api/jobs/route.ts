import {
  workplaceKey,
  experienceLabels,
  jobExperience,
  sortPublicJobs,
  type ExperienceKind,
} from "@/lib/job-filters";
import { collectedJobs } from "@/lib/server/job-feed";
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
    !["all", "ax", "ml", "data"].includes(role)
  )
    return Response.json({ error: "잘못된 조회 조건입니다." }, { status: 400 });
  try {
    const feed = await collectedJobs();
    const filtered = feed.jobs.filter(
      (job) =>
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
          .includes(query),
    );
    const sorted = sortPublicJobs(filtered, sort);
    return Response.json(
      {
        ...feed,
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
