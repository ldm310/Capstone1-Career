import { experienceLabels, type ExperienceKind } from "./job-filters";
export type CatalogState = {
  query: string;
  role: string;
  location: string;
  workplace: string;
  sort: string;
  experience: ExperienceKind[];
  pageSize: number;
  offset: number;
};
export function catalogState(params: URLSearchParams): CatalogState {
  const pageSize = params.get("limit") === "24" ? 24 : 12;
  const offset = Number(params.get("offset") || 0);
  return {
    query: (params.get("q") || "").slice(0, 200),
    role: ["all", "data", "backend"].includes(params.get("role") || "")
      ? params.get("role")!
      : "all",
    location: (params.get("location") || "").slice(0, 100),
    workplace: ["all", "remote", "hybrid", "on-site", "unknown"].includes(
      params.get("workplace") || "",
    )
      ? params.get("workplace")!
      : "all",
    sort: ["newest", "closing", "company"].includes(params.get("sort") || "")
      ? params.get("sort")!
      : "newest",
    experience: (params.get("experience") || "")
      .split(",")
      .filter((value) =>
        Object.hasOwn(experienceLabels, value),
      ) as ExperienceKind[],
    pageSize,
    offset:
      Number.isSafeInteger(offset) && offset >= 0 && offset <= 100000
        ? Math.floor(offset / pageSize) * pageSize
        : 0,
  };
}
export function catalogUrl(state: CatalogState) {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.role !== "all") params.set("role", state.role);
  if (state.location) params.set("location", state.location);
  if (state.workplace !== "all") params.set("workplace", state.workplace);
  if (state.sort !== "newest") params.set("sort", state.sort);
  if (state.experience.length)
    params.set("experience", state.experience.join(","));
  if (state.pageSize !== 12) params.set("limit", String(state.pageSize));
  if (state.offset) params.set("offset", String(state.offset));
  return "/jobs" + (params.size ? "?" + params.toString() : "");
}
export function jobDetailUrl(catalog: string, id: string, stats = false) {
  const url = new URL(catalog, "https://career.invalid");
  url.searchParams.set("job", id);
  if (stats) url.searchParams.set("view", "stats");
  return url.pathname + url.search;
}
export function catalogBackUrl(params: URLSearchParams) {
  const next = new URLSearchParams(params);
  next.delete("job");
  next.delete("view");
  return "/jobs" + (next.size ? "?" + next.toString() : "");
}
