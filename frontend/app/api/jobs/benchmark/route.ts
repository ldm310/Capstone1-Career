import { createHiringCohort } from "@/mock/hiring-cohort";
import { studyDemoJobs } from "@/lib/study-prototype";
import { dummyJobs } from "@/lib/dummy-jobs";

export function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const jobId = params.get("jobId")?.trim();
  if (!jobId || jobId.length > 200)
    return Response.json(
      { error: "잘못된 비교 조회 조건입니다." },
      { status: 400 },
    );
  const { people, passed, source, version } = createHiringCohort(jobId);
  const example = [...studyDemoJobs, ...dummyJobs].find(
    (job) => job.id === jobId,
  );
  const synthetic = !!example;
  // Fixture states belong to distinct fictional jobs, never a user-selected toggle.
  const noPeople =
    jobId === "study-demo-backend-intern" || jobId === "dummy:server-intern";
  const noPassed =
    jobId === "study-demo-data" || jobId === "dummy:data-engineer";
  const applicants =
    !synthetic || noPeople
      ? []
      : noPassed
        ? people.filter((person) => person.outcome !== "passed")
        : people;
  const skills = example?.skills ?? ["Java", "Spring Boot", "SQL"];
  return Response.json(
    {
      source: synthetic ? source : "UNAVAILABLE",
      version,
      jobId,
      applicants,
      passed: !synthetic || noPeople || noPassed ? [] : passed,
      qualifications: synthetic
        ? [
            { text: `${skills[0]} 활용 경험`, status: "met" },
            { text: `${skills[1]} 프로젝트 경험`, status: "met" },
            { text: `${skills[2]} 활용 경험`, status: "missing" },
            { text: "프로젝트 결과 설명 가능", status: "met" },
          ]
        : [],
      note: synthetic
        ? "화면 확인용 가상 데이터이며 실제 합격자 통계가 아닙니다."
        : "연결된 비교·지원 자격 평가 자료가 없습니다.",
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
