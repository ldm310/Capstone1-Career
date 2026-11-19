import { createHiringCohort } from "@/mock/hiring-cohort";

export function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const jobId = params.get("jobId")?.trim();
  const cohort = params.get("cohort") ?? "available";
  if (!jobId || jobId.length > 200 || !["available", "empty"].includes(cohort))
    return Response.json(
      { error: "잘못된 비교 조회 조건입니다." },
      { status: 400 },
    );
  const { people, passed, source, version } = createHiringCohort(jobId);
  // The empty scenario includes no successful profiles in either comparison pool.
  const applicants =
    cohort === "empty"
      ? people.filter((person) => person.outcome !== "passed")
      : people;
  return Response.json(
    {
      source,
      version,
      jobId,
      applicants,
      passed: cohort === "empty" ? [] : passed,
      note: "화면 확인용 가상 데이터이며 실제 합격자 통계가 아닙니다.",
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
