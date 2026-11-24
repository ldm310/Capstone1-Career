import { redirect, notFound } from "next/navigation";
import { user, isGuest } from "@/lib/server/store";
import { memberRole } from "@/lib/server/notices";
import { ExtractionReviewBoard } from "@/components/admin/extraction-review-board";
import { NoticeBoard } from "@/components/notices/notice-board";
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
  return tab === "notices" ? <NoticeBoard /> : <ExtractionReviewBoard />;
}
