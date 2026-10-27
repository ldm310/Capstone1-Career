"use client";
import { useSearchParams } from "next/navigation";
import { LiveJobsSection } from "@/components/landing/live-jobs-section";
import { JobDetail } from "@/components/jobs/job-detail";
import { ExampleJobs } from "@/components/jobs/example-jobs";
import { studyTier } from "@/lib/study-prototype";
export default function Jobs() {
  const params = useSearchParams();
  const job = params.get("job");
  const tier = studyTier(params.get("demo"));
  if (job) return <JobDetail key={`${job}:${tier}`} id={job} />;
  if (tier) return <ExampleJobs tier={tier} />;
  return (
    <LiveJobsSection
      mode="catalog"
      initialSavedOnly={params.get("tab") === "saved"}
    />
  );
}
