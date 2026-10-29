import { classifyJobRole, type SupportedRole } from "@/lib/roles";
import {
  unknownLocation,
  type PostingSection,
  type PublicJob,
} from "@/types/public-job";

// 백엔드(Spring) 채용공고 API를 프론트 공고 형식으로 바꾼다.
// BACKEND_URL이 없거나 백엔드가 응답하지 않으면 빈 목록을 돌려 기존 공고만 보여준다.

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
}
export interface BackendPostingDetail extends BackendPostingSummary {
  site: string;
  sitePostingNo: string;
  minYears: number | null;
  collectedAt: string;
  lastCheckedAt: string;
  analysis: {
    recruitUnits: {
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

async function get<T>(path: string): Promise<T> {
  const base = backendUrl();
  if (!base) throw new Error("BACKEND_URL이 없어요.");
  const response = await fetch(base + path, {
    signal: AbortSignal.timeout(5000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`백엔드 응답 ${response.status}`);
  return response.json() as Promise<T>;
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

function experience(p: BackendPostingDetail): PublicJob["experience"] {
  const careers = new Set(
    (p.analysis?.recruitUnits ?? []).map((u) => u.career),
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
  const units = p.analysis?.recruitUnits ?? [];
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
      (p.analysis?.recruitUnits ?? []).flatMap((u) =>
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
  return p.site === "saramin"
    ? `https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=${encodeURIComponent(p.sitePostingNo)}`
    : "";
}

export function toPublicJob(p: BackendPostingDetail): PublicJob | null {
  const category = role(p);
  if (!category) return null;
  return {
    id: `be:${p.postingId}`,
    company: p.companyName,
    title: p.title,
    category,
    // 백엔드에는 근무지가 없다. 지어내지 않고 원문 확인으로 둔다.
    location: unknownLocation,
    employment: p.employmentType || "고용 형태 원문 확인",
    workplace: null,
    postedAt: p.collectedAt,
    closesAt: p.deadline ? `${p.deadline}T23:59:59+09:00` : null,
    experience: experience(p),
    url: originalUrl(p),
    skills: postingSkills(p),
    posting: postingSections(p),
  };
}

// 진행 중 공고를 최대 200개까지 읽고, 상세(추출 결과)를 8개씩 나눠 받는다.
async function load(): Promise<PublicJob[]> {
  const summaries: BackendPostingSummary[] = [];
  for (let page = 0; page < 2; page++) {
    const data = await get<BackendPage<BackendPostingSummary>>(
      `/api/postings?status=${encodeURIComponent("진행")}&page=${page}&size=100`,
    );
    summaries.push(...data.content);
    if (page + 1 >= data.totalPages) break;
  }
  const wanted = summaries.filter((s) => role(s));
  const jobs: PublicJob[] = [];
  for (let i = 0; i < wanted.length; i += 8) {
    const details = await Promise.all(
      wanted
        .slice(i, i + 8)
        .map((s) =>
          get<BackendPostingDetail>(`/api/postings/${s.postingId}`).catch(
            () => null,
          ),
        ),
    );
    for (const d of details) {
      const job = d && toPublicJob(d);
      if (job) jobs.push(job);
    }
  }
  return jobs;
}

// at: 이 시각까지 캐시를 쓴다.
let cache: { at: number; jobs: PublicJob[] } | null = null;
// 5분 동안 같은 결과를 쓴다. 실패하면 마지막 결과(없으면 빈 목록)를 쓰고 30초 뒤에 다시 시도한다.
export async function backendJobs(): Promise<PublicJob[]> {
  if (!backendUrl()) return [];
  if (cache && Date.now() < cache.at) return cache.jobs;
  try {
    cache = { at: Date.now() + 300_000, jobs: await load() };
  } catch {
    cache = { at: Date.now() + 30_000, jobs: cache?.jobs ?? [] };
  }
  return cache.jobs;
}
