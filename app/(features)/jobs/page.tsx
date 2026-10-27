"use client";
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LiveJobsSection } from "@/components/landing/live-jobs-section";
import { JobDetail } from "@/components/jobs/job-detail";
import { ExampleJobs } from "@/components/jobs/example-jobs";
import { studyTier } from "@/lib/study-prototype";
export default function Jobs() {
  const params = useSearchParams();
  const router = useRouter();
  // 저장한 공고는 마이페이지로 옮겼다.
  const savedTab = params.get("tab") === "saved";
  useEffect(() => {
    if (savedTab) router.replace("/my-page");
  }, [savedTab, router]);
  const job = params.get("job");
  const tier = studyTier(params.get("demo"));
  if (job) return <JobDetail key={`${job}:${tier}`} id={job} />;
  if (tier) return <ExampleJobs tier={tier} />;
  if (savedTab) return null;
  return <LiveJobsSection mode="catalog" />;
}
