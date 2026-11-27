"use client";
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LiveJobsSection } from "@/components/landing/live-jobs-section";
import { JobDetail } from "@/components/jobs/job-detail";
import { studyTier } from "@/lib/study-prototype";
import {
  catalogState,
  catalogUrl,
  type CatalogState,
} from "@/lib/catalog-navigation";
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
  if (savedTab) return null;
  const state = catalogState(new URLSearchParams(params.toString()));
  function update(patch: Partial<CatalogState>) {
    const next = {
      ...catalogState(new URLSearchParams(window.location.search)),
      ...patch,
    };
    window.history.replaceState(null, "", catalogUrl(next));
  }
  return <LiveJobsSection mode="catalog" catalog={{ state, update }} />;
}
