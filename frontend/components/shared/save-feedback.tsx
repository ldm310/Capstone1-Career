"use client";
import type { SaveResult } from "@/lib/saved-jobs";
export function SaveFeedback({
  result,
  onDismiss,
}: {
  result: SaveResult | null;
  onDismiss: () => void;
}) {
  if (!result) return null;
  return (
    <aside
      className={"save-feedback" + (result.ok ? "" : " is-error")}
      role={result.ok ? "status" : "alert"}
    >
      <p>{result.message}</p>
      <button type="button" aria-label="저장 알림 닫기" onClick={onDismiss}>
        닫기
      </button>
    </aside>
  );
}
