import { ExternalLink } from "lucide-react";
import type { PublicJob } from "@/types/public-job";

// 원문 주소: 더미, 예시 공고는 가상 원문 페이지로, 실제 공고는 수집한 주소로 연결한다.
export function originalUrl(job: PublicJob) {
  if (job.dummy) return `/postings/${encodeURIComponent(job.id)}`;
  return job.url || null;
}

export function OriginalLink({
  job,
  className,
  label = "원문 보기",
}: {
  job: PublicJob;
  className?: string;
  label?: string;
}) {
  const href = originalUrl(job);
  if (!href)
    return (
      <span className={`original-missing ${className ?? ""}`}>
        원문을 찾을 수 없습니다.
      </span>
    );
  return (
    <a
      className={className}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {label} <ExternalLink size={14} />
      <span className="sr-only"> (새 창)</span>
    </a>
  );
}
