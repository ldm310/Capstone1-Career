export function workplaceKey(value: string | null) {
  const text = (value || "").toLowerCase();
  if (/hybrid|하이브리드|혼합/.test(text)) return "hybrid";
  if (/remote|원격|재택/.test(text)) return "remote";
  if (/on.?site|사무실|오피스|현장/.test(text)) return "on-site";
  return "unknown";
}

export const experienceLabels = {
  entry: "신입",
  experienced: "경력",
  intern: "인턴",
  any: "경력 무관",
} as const;
export type ExperienceKind = keyof typeof experienceLabels;

export function jobExperience(job: {
  experience?: ExperienceKind[];
  title: string;
  employment: string;
}): ExperienceKind[] {
  if (job.experience) return job.experience;
  // Do not infer seniority from a technology, company or full-time employment.
  const text = `${job.title} ${job.employment}`;
  const result: ExperienceKind[] = [];
  if (/경력\s*무관|신입\s*[\/·]\s*경력/i.test(text)) result.push("any");
  if (/신입|entry.?level|new.?grad/i.test(text)) result.push("entry");
  if (/경력(?!\s*무관)|senior|staff|principal/i.test(text))
    result.push("experienced");
  if (/인턴|intern\b|internship/i.test(text)) result.push("intern");
  return result;
}

export function sortPublicJobs<
  T extends {
    postedAt: string | null;
    closesAt?: string | null;
    company: string;
  },
>(jobs: T[], sort: string): T[] {
  const time = (value: string | null | undefined, fallback: number) => {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : fallback;
  };
  return [...jobs].sort((a, b) =>
    sort === "closing"
      ? time(a.closesAt, Infinity) - time(b.closesAt, Infinity)
      : sort === "company"
        ? a.company.localeCompare(b.company, "ko")
        : time(b.postedAt, 0) - time(a.postedAt, 0),
  );
}
