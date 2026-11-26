import { redirect, notFound } from "next/navigation";
import { user, isGuest } from "@/lib/server/store";
import { memberRole } from "@/lib/server/notices";
import { ExtractionReviewBoard } from "@/components/admin/extraction-review-board";
import { NoticeBoard } from "@/components/notices/notice-board";
import { ClosedPostingsBoard } from "@/components/admin/closed-postings-board";
import { PostingPublicationBoard } from "@/components/admin/posting-publication-board";
import "../../admin-review.css";
import "../../notices.css";

export default async function Admin({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const current = await user();
  if (!current || isGuest(current.id)) redirect("/sign-in");
  if ((await memberRole(current.id)) !== "ADMIN") notFound();
  const { tab } = await searchParams;
  return tab === "postings" ? (
    <PostingPublicationBoard />
  ) : tab === "skipped" ? (
    <ExtractionReviewBoard archive />
  ) : tab === "closed" ? (
    <ClosedPostingsBoard />
  ) : tab === "notices" ? (
    <NoticeBoard />
  ) : (
    <ExtractionReviewBoard />
  );
}
