export type ReviewStatus = "OPEN" | "SKIPPED" | "RETRY_REQUESTED" | "RESOLVED";
export interface ReviewItem {
  id: string;
  postingNo: string;
  site: string;
  company: string;
  title: string;
  sourceUrl: string;
  status: ReviewStatus;
  feedback: string;
  updatedAt: string;
  revision: string;
  reviewReasons: Array<Record<string, unknown>>;
  deadline?: string | null;
  deadlinePassed?: boolean;
  sourceClosed?: boolean;
}
export type ReviewAction = "PASS" | "RETRY" | "APPROVE" | "RESTORE";
export interface StoredReviewUnit {
  id: string;
  name: string;
  isIt: boolean;
  job: string | null;
  career: string;
  years: string;
  items: { category: string; text: string; quote: string }[];
}
export interface ExtractionReviewDetail {
  review: ReviewItem;
  posting: {
    id: string;
    bodyHtml: string | null;
    lastCheckedAt: string;
    images: { seq: number; url: string; kept: boolean | null }[];
  };
  extraction: {
    id: string;
    isCurrent: boolean;
    model: string;
    promptVersion: string;
    dictVersion: string;
    runAt: string;
    rawOutput: unknown | null;
    units: StoredReviewUnit[];
  };
}
