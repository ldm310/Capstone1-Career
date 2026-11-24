"use client";
import { useSearchParams } from "next/navigation";
import { selectedSectionTab } from "@/lib/feature-sections";
import { SavedJobsPanel } from "@/components/my-page/saved-jobs-panel";
import { ProfilePanel } from "@/components/my-page/profile-panel";
export default function MyPage() {
  const tab = selectedSectionTab("mypage", useSearchParams().get("tab"));
  return tab === "profile" ? <ProfilePanel /> : <SavedJobsPanel />;
}
