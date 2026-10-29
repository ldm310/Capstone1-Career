import { classifyJobRole } from "@/lib/roles";
import { patterns } from "@/lib/skill-patterns";
import type { PublicJob } from "@/types/public-job";
const boards = [
  { id: "zoyi", company: "채널코퍼레이션" },
  { id: "matchgroup", company: "매치그룹" },
];
const record = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" ? (v as Record<string, unknown>) : {};
const string = (v: unknown) => (typeof v === "string" ? v : "");
function normalize(
  value: unknown,
  board: (typeof boards)[number],
): PublicJob | null {
  const raw = record(value),
    categories = record(raw.categories);
  const title = string(raw.text),
    location = string(categories.location);
  const category = classifyJobRole(title);
  if (
    !category ||
    !(raw.country === "KR" || /seoul|korea|서울|한국/i.test(location))
  )
    return null;
  let url: URL;
  try {
    url = new URL(string(raw.hostedUrl));
  } catch {
    return null;
  }
  if (
    url.protocol !== "https:" ||
    url.hostname !== "jobs.lever.co" ||
    !url.pathname.startsWith(`/${board.id}/`) ||
    !string(raw.id)
  )
    return null;
  const timestamp =
    typeof raw.createdAt === "number" ? new Date(raw.createdAt) : null;
  return {
    id: `${board.id}:${raw.id}`,
    skills: Object.entries(patterns)
      .filter(([, regex]) =>
        regex.test(
          [
            string(raw.descriptionPlain),
            string(raw.additionalPlain),
            JSON.stringify(raw.lists ?? []),
          ].join("\n"),
        ),
      )
      .map(([name]) => name),
    company: board.company,
    title,
    category,
    location: /gangnam/i.test(location)
      ? "서울 강남구"
      : /seoul/i.test(location)
        ? "서울"
        : location || "근무지 원문 확인",
    employment: /full.?time/i.test(string(categories.commitment))
      ? "정규직"
      : string(categories.commitment) || "고용형태 원문 확인",
    workplace:
      raw.workplaceType === "hybrid"
        ? "하이브리드 근무"
        : raw.workplaceType === "remote"
          ? "원격 근무"
          : raw.workplaceType === "on-site"
            ? "사무실 근무"
            : null,
    postedAt:
      timestamp && Number.isFinite(timestamp.getTime())
        ? timestamp.toISOString()
        : null,
    url: url.href,
  };
}
export async function getPublicJobs() {
  const results = await Promise.allSettled(
    boards.map(async (board) => {
      const response = await fetch(
        `https://api.lever.co/v0/postings/${board.id}?mode=json`,
        { cache: "no-store", signal: AbortSignal.timeout(10000) },
      );
      if (!response.ok) throw new Error("Source unavailable");
      const body: unknown = await response.json();
      if (!Array.isArray(body)) throw new Error("Invalid source");
      return body
        .map((value) => normalize(value, board))
        .filter((job): job is PublicJob => job !== null);
    }),
  );
  if (results.every((result) => result.status === "rejected"))
    throw new Error(
      "채용공고를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.",
    );
  const jobs = results
    .flatMap((result) => (result.status === "fulfilled" ? result.value : []))
    .sort(
      (a, b) =>
        (b.postedAt ?? "").localeCompare(a.postedAt ?? "") ||
        a.id.localeCompare(b.id),
    );
  return {
    jobs,
    checkedAt: new Date().toISOString(),
    unavailableSources: boards
      .filter((_, i) => results[i].status === "rejected")
      .map((board) => board.company),
  };
}
