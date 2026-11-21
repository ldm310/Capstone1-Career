import type { DemoCandidate } from "@/mock/hiring-cohort";

export interface QualificationCheck {
  text: string;
  status: "met" | "missing" | "unknown";
}
export interface JobBenchmark {
  source: "SYNTHETIC" | "UNAVAILABLE";
  jobId: string;
  applicants: DemoCandidate[];
  passed: DemoCandidate[];
  qualifications: QualificationCheck[];
}

// Equal weighting of explicitly assessed mandatory requirements only.
// Unknown requirements prevent a final score rather than counting as failures.
export function qualificationScore(checks: QualificationCheck[]) {
  if (!checks.length || checks.some((check) => check.status === "unknown"))
    return null;
  return Math.round(
    (checks.filter((check) => check.status === "met").length / checks.length) *
      100,
  );
}
