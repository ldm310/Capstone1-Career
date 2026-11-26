import { classifyJobRole, type SupportedRole } from "@/lib/roles";
import { openPostingSql } from "./posting-metadata-sql";
import { parsePostingMetadata } from "./posting-metadata";
import {
  unknownLocation,
  type PostingSection,
  type PublicJob,
} from "@/types/public-job";

// 백엔드(Spring) 채용 공고 API를 프론트 공고 형식으로 바꾼다.
// 목록 검색은 job-catalog.ts의 DB 페이지 조회, 상세는 이 어댑터를 사용한다.

// 백엔드 응답 형식: backend/src/main/java/com/career/backend/domain/posting/*Response.java
export interface BackendPage<T> {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}
export interface BackendPostingSummary {
  postingId: number;
  companyName: string;
  title: string;
  siteJobCategory: string | null;
  careerCondition: string | null;
  employmentType: string | null;
  kind: string;
  status: string;
  deadline: string | null;
  skillCategories?: string[] | null;
}
export interface BackendPostingDetail extends BackendPostingSummary {
  site: string;
  sitePostingNo: string;
  minYears: number | null;
  collectedAt: string;
  lastCheckedAt: string;
  analysis: {
    recruitUnits: {
      isIt?: boolean;
      it?: boolean;
      job?: string | null;
      name: string;
      career: string;
      items: {
        category: "필수" | "우대" | "업무" | "기타";
        seq: number;
        text: string;
        requirements: {
          capabilityName: string | null;
          otherName: string | null;
          techs: { techName: string | null; writtenName: string }[];
        }[];
      }[];
    }[];
  } | null;
}

export function backendUrl() {
  return process.env.BACKEND_URL?.replace(/\/+$/, "") || null;
}

// 상세 링크는 공고 ID로 직접 조회한다.
export async function backendJob(postingId: number): Promise<PublicJob | null> {
  if (!Number.isSafeInteger(postingId) || postingId < 1)
    throw new Error("잘못된 공고 ID입니다.");
  const base = backendUrl();
  if (!base) throw new Error("BACKEND_URL이 없어요.");
  let metadata: ReturnType<typeof parsePostingMetadata> | undefined;
  if (process.env.CAREER_PROFILE_DATABASE_URL) {
    const pool = (await import("./posting-levels")).profilePool();
    const result = await pool!.query(
      `SELECT body_html FROM public.posting p WHERE p.id=$1 AND ${openPostingSql("p")}`,
      [postingId],
    );
    if (!result.rowCount) return null;
    metadata = parsePostingMetadata(result.rows[0].body_html || "");
  }
  const response = await fetch(`${base}/api/postings/${postingId}`, {
    signal: AbortSignal.timeout(5000),
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`백엔드 응답 ${response.status}`);
  const job = toPublicJob((await response.json()) as BackendPostingDetail);
  return job && metadata
    ? {
        ...job,
        location: metadata.location || unknownLocation,
        workplace: metadata.workplace,
      }
    : job;
}

// The legacy job-analysis form resolves a single source URL without loading a list.
export async function backendJobBySourceUrl(
  value: string,
): Promise<(PublicJob & { posting: PostingSection[] }) | null> {
  let source: URL;
  try {
    source = new URL(value);
  } catch {
    return null;
  }
  const postingNo = source.searchParams.get("rec_idx");
  if (
    source.protocol !== "https:" ||
    source.hostname !== "www.saramin.co.kr" ||
    !postingNo ||
    !/^[0-9]+$/.test(postingNo)
  )
    return null;
  const { profilePool } = await import("./posting-levels");
  const database = profilePool();
  if (!database) return null;
  const { rows } = await database.query(
    "SELECT id FROM public.posting WHERE site IN ('사람인','saramin') AND site_posting_no=$1 LIMIT 1",
    [postingNo],
  );
  const job = rows[0]
    ? await backendJob(Number(rows[0].id)).catch(() => null)
    : null;
  return job?.posting?.length ? { ...job, posting: job.posting } : null;
}

// 프론트가 다루는 직무(데이터, 백엔드)만 남긴다. 제목을 먼저 보고, 없으면 사람인 직무 분류를 본다.
function role(p: BackendPostingSummary): SupportedRole | null {
  const byTitle = classifyJobRole(p.title);
  if (byTitle) return byTitle;
  const category = p.siteJobCategory ?? "";
  if (/데이터/.test(category)) return "data";
  if (/백엔드|서버/.test(category)) return "backend";
  return null;
}

type BackendUnit = NonNullable<
  BackendPostingDetail["analysis"]
>["recruitUnits"][number];
function targetUnit(unit: BackendUnit) {
  return (
    unit.it !== false &&
    unit.isIt !== false &&
    (unit.job === undefined ||
      unit.job === "백엔드" ||
      unit.job === "데이터 엔지니어")
  );
}

function experience(p: BackendPostingDetail): PublicJob["experience"] {
  const careers = new Set(
    (p.analysis?.recruitUnits ?? []).filter(targetUnit).map((u) => u.career),
  );
  const text = `${p.careerCondition ?? ""} ${[...careers].join(" ")}`;
  const result: NonNullable<PublicJob["experience"]> = [];
  if (/무관/.test(text)) result.push("any");
  if (/신입/.test(text) || p.minYears === 0) result.push("entry");
  if (/경력/.test(text)) result.push("experienced");
  if (/인턴/.test(`${p.employmentType ?? ""} ${p.title}`))
    result.push("intern");
  return result.length ? [...new Set(result)] : undefined;
}

const sectionTitles = {
  업무: "주요 업무",
  필수: "자격요건",
  우대: "우대사항",
  기타: "기타",
} as const;

// 추출 결과(모집 단위 → 항목)를 공고 본문 섹션으로 묶는다. 모집 단위가 여럿이면 항목 앞에 단위 이름을 붙인다.
export function postingSections(p: BackendPostingDetail): PostingSection[] {
  const units = (p.analysis?.recruitUnits ?? []).filter(targetUnit);
  return (Object.keys(sectionTitles) as (keyof typeof sectionTitles)[])
    .map((category) => ({
      title: sectionTitles[category],
      items: units.flatMap((u) =>
        u.items
          .filter((i) => i.category === category)
          .sort((a, b) => a.seq - b.seq)
          .map((i) => (units.length > 1 ? `[${u.name}] ${i.text}` : i.text)),
      ),
    }))
    .filter((s) => s.items.length);
}

// 공고 기술: 사전에 있는 이름(techName)을 쓰고, 없으면 공고에 적힌 이름을 쓴다.
export function postingSkills(p: BackendPostingDetail) {
  return [
    ...new Set(
      (p.analysis?.recruitUnits ?? [])
        .filter(targetUnit)
        .flatMap((u) =>
          u.items.flatMap((i) =>
            i.requirements.flatMap((r) =>
              r.techs.map((t) => t.techName ?? t.writtenName),
            ),
          ),
        ),
    ),
  ];
}

function originalUrl(p: BackendPostingDetail) {
  return ["saramin", "사람인"].includes(p.site)
    ? `https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=${encodeURIComponent(p.sitePostingNo)}`
    : "";
}

export function toPublicJob(p: BackendPostingDetail): PublicJob | null {
  const jobs = new Set(
    (p.analysis?.recruitUnits ?? []).filter(targetUnit).map((unit) => unit.job),
  );
  const category =
    jobs.has("데이터 엔지니어") && !jobs.has("백엔드")
      ? "data"
      : jobs.has("백엔드") && !jobs.has("데이터 엔지니어")
        ? "backend"
        : role(p) ?? (jobs.has("백엔드") ? "backend" : null);
  const sections = postingSections(p)
    .map((section) => ({
      ...section,
      items: section.items.filter((text) => text.trim().length > 0),
    }))
    .filter((section) => section.items.length > 0);
  if (!category || !sections.length) return null;
  return {
    id: `be:${p.postingId}`,
    company: p.companyName,
    title: p.title,
    category,
    skillCategories: p.skillCategories ?? null,
    // 백엔드에는 근무지가 없다. 지어내지 않고 원문 확인으로 둔다.
    location: unknownLocation,
    employment: p.employmentType || "고용 형태 원문 확인",
    workplace: null,
    postedAt: p.collectedAt,
    closesAt: p.deadline ? `${p.deadline}T23:59:59+09:00` : null,
    experience: experience(p),
    url: originalUrl(p),
    skills: postingSkills(p),
    posting: sections,
  };
}
