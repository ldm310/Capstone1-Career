"use client";
import { useSearchParams } from "next/navigation";
import { CareerWorkspace } from "@/components/career/workspace";
import { LiveJobsSection } from "@/components/landing/live-jobs-section";
export default function Jobs() {
  const tab = useSearchParams().get("tab");
  return tab === "jobs" ? (
    <CareerWorkspace section="jobs" />
  ) : (
    <LiveJobsSection mode="catalog" initialSavedOnly={tab === "saved"} />
  );
}
