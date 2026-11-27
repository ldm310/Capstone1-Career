"use client";
import { useEffect, useMemo, useState } from "react";
import type {
  ExtractionReviewDetail,
  ReviewAction,
  ReviewItem,
} from "@/types/extraction-review";
import {
  reviewSourceDocument,
  safeSourceUrl,
} from "@/lib/review-source-preview";
import { ReviewReason } from "./review-reason";

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
const text = (value: unknown) =>
  typeof value === "string"
    ? value
    : typeof value === "number"
      ? String(value)
      : "";
const records = (value: unknown) =>
  Array.isArray(value)
    ? value.map(record).filter((r): r is Record<string, unknown> => r !== null)
    : [];
const groups = [
  ["required", "자격요건"],
  ["preferred", "우대사항"],
  ["duties", "담당업무"],
  ["other", "기타"],
] as const;
const time = (value: string) =>
  new Date(value).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
function LlmResult({ value }: { value: unknown }) {
  const raw = record(value);
  if (!raw)
    return (
      <p className="review-detail-empty">
        LLM 원본이 저장되지 않았거나 구조화 형식이 아닙니다. DB 저장 결과와 JSON
        원본을 확인해 주세요.
      </p>
    );
  const positions = records(raw.positions);
  return (
    <>
      {positions.length ? (
        positions.map((unit, index) => (
          <section className="review-extracted-unit" key={index}>
            <header>
              <h4>{text(unit.name) || `모집 직무 ${index + 1}`}</h4>
              <p>
                {[
                  text(unit.job),
                  text(unit.career),
                  text(unit.years),
                  unit.it_job === false ? "IT 직무 아님" : "",
                ]
                  .filter(Boolean)
                  .join(", ")}
              </p>
            </header>
            {groups.map(([key, label]) => {
              const items = records(unit[key]);
              return (
                <section className="review-item-group" key={key}>
                  <h5>
                    {label} <span>{items.length}개</span>
                  </h5>
                  {items.length ? (
                    <ul>
                      {items.map((item, i) => (
                        <li key={i}>
                          <p>{text(item.text) || "추출 문장 없음"}</p>
                          {records(item.reqs).length > 0 && (
                            <p className="review-requirements">
                              {records(item.reqs)
                                .map((req) =>
                                  [
                                    text(req.capability),
                                    text(req.other_name),
                                    ...(Array.isArray(req.techs)
                                      ? req.techs.map(text)
                                      : []),
                                  ]
                                    .filter(Boolean)
                                    .join(", "),
                                )
                                .join(" / ")}
                            </p>
                          )}
                          {text(item.quote) && (
                            <details>
                              <summary>근거 원문</summary>
                              <blockquote>{text(item.quote)}</blockquote>
                            </details>
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="review-field-empty">추출 항목 없음</p>
                  )}
                </section>
              );
            })}
          </section>
        ))
      ) : (
        <p className="review-detail-empty">
          LLM 응답에 추출된 모집 직무가 없습니다.
        </p>
      )}
      {Array.isArray(raw.skipped) && raw.skipped.length > 0 && (
        <section className="review-extracted-unit">
          <h4>LLM이 제외한 내용</h4>
          <ul>
            {raw.skipped.map((item, i) => (
              <li key={i}>
                {typeof item === "string" ? item : JSON.stringify(item)}
              </li>
            ))}
          </ul>
        </section>
      )}
      {text(raw.notes) && (
        <section className="review-extracted-unit">
          <h4>LLM 메모</h4>
          <p>{text(raw.notes)}</p>
        </section>
      )}
    </>
  );
}
function SourcePane({ detail }: { detail: ExtractionReviewDetail }) {
  const [view, setView] = useState<"html" | "images">("html");
  const html = useMemo(
    () => reviewSourceDocument(detail.posting.bodyHtml || ""),
    [detail.posting.bodyHtml],
  );
  const images = detail.posting.images.filter((image) =>
    safeSourceUrl(image.url),
  );
  return (
    <section className="review-compare-pane" aria-label="공고 원문">
      <div className="review-pane-heading">
        <h3>공고 원문</h3>
        <div
          className="review-detail-tabs"
          role="group"
          aria-label="원문 표시 방식"
        >
          <button
            aria-pressed={view === "html"}
            onClick={() => setView("html")}
          >
            본문
          </button>
          <button
            aria-pressed={view === "images"}
            onClick={() => setView("images")}
          >
            이미지 {images.length}
          </button>
        </div>
      </div>
      <p className="review-pane-note">
        RDS의 현재 저장본, 마지막 확인 {time(detail.posting.lastCheckedAt)}
      </p>
      <div className="review-pane-content">
        {view === "html" && detail.posting.bodyHtml?.trim() ? (
          <iframe
            title="저장된 공고 원문"
            sandbox=""
            referrerPolicy="no-referrer"
            srcDoc={html}
          />
        ) : images.length ? (
          <div className="review-source-images">
            {!detail.posting.bodyHtml?.trim() && view === "html" && (
              <p>저장된 본문이 없어 원문 이미지를 표시합니다.</p>
            )}
            {images.map((image, index) => (
              <figure key={image.seq}>
                <figcaption>
                  이미지 {index + 1}
                  {image.kept === false ? ", 추출 전 제외된 이미지" : ""}
                </figcaption>
                {/* Original source images have variable dimensions and external origins. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={safeSourceUrl(image.url)!}
                  alt={`공고 원문 이미지 ${index + 1}`}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              </figure>
            ))}
          </div>
        ) : (
          <p className="review-detail-empty">
            저장된 {view === "html" ? "원문과 이미지가" : "이미지가"} 없습니다.
            상단의 공고 원문 링크에서 확인해 주세요.
          </p>
        )}
      </div>
    </section>
  );
}
export function ExtractionReviewDetailView({
  id,
  busy,
  actionError,
  onClose,
  onDecision,
}: {
  id: string;
  busy: boolean;
  actionError: string;
  onClose: () => void;
  onDecision: (
    item: ReviewItem,
    action: ReviewAction,
    feedback: string,
  ) => Promise<void>;
}) {
  const [detail, setDetail] = useState<ExtractionReviewDetail | null>(null),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const [view, setView] = useState<"llm" | "stored" | "json">("llm"),
    [feedback, setFeedback] = useState(""),
    [editing, setEditing] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        setError("");
        setDetail(null);
        const response = await fetch(
          `/api/admin/extraction-reviews/${encodeURIComponent(id)}`,
          { signal: controller.signal, cache: "no-store" },
        );
        const data = await response.json();
        if (!response.ok)
          throw new Error(data.error || "비교 자료를 불러오지 못했습니다.");
        if (!controller.signal.aborted) {
          setDetail(data);
          setFeedback(data.review.feedback || "");
        }
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "조회 오류");
      }
    })();
    return () => controller.abort();
  }, [id, retry]);
  const item = detail?.review;
  const canReview = detail?.extraction.isCurrent && item?.status === "OPEN";
  const expired = item?.deadlinePassed || item?.sourceClosed;
  const url = item && safeSourceUrl(item.sourceUrl);
  return (
    <section
      id="review-detail"
      className="review-detail-page"
      aria-label="공고 추출 비교"
    >
      <header className="review-detail-header">
        <div>
          <p>{item?.company || "추출 검토"}</p>
          <h2 id="review-detail-title">
            {item?.title || "원문과 LLM 결과 비교"}
          </h2>
          {detail && (
            <p>
              공고 {item?.postingNo}, 추출 실행 {detail.extraction.id},{" "}
              {time(detail.extraction.runAt)} / {detail.extraction.model}
            </p>
          )}
        </div>
        <div>
          {url && (
            <a href={url} target="_blank" rel="noopener noreferrer">
              공고 원문 열기
            </a>
          )}
          <button disabled={busy} onClick={onClose}>
            뒤로가기
          </button>
        </div>
      </header>
      <div className="review-detail-body">
        {error ? (
          <div role="alert" className="career-error">
            <p>{error}</p>
            <button onClick={() => setRetry((v) => v + 1)}>
              다시 불러오기
            </button>
          </div>
        ) : !detail ? (
          <p role="status" className="review-detail-empty">
            원문과 LLM 결과를 불러오는 중…
          </p>
        ) : (
          <>
            <section
              className="review-detail-reasons"
              aria-label="상세 검토 사유"
            >
              <h3>검토 사유 {item!.reviewReasons.length}개</h3>
              <ul>
                {item!.reviewReasons.map((reason, i) => (
                  <li key={i}>
                    <ReviewReason reason={reason} />
                  </li>
                ))}
              </ul>
            </section>
            {!detail.extraction.isCurrent && (
              <p className="review-policy">
                새 추출 결과가 저장되어 이 실행은 현재 결과가 아닙니다. 목록을
                새로고침한 뒤 최신 결과를 검토해 주세요.
              </p>
            )}
            <div className="review-compare-grid">
              <SourcePane detail={detail} />
              <section
                className="review-compare-pane"
                aria-label="LLM 추출 결과"
              >
                <div className="review-pane-heading">
                  <h3>LLM 추출 결과</h3>
                  <div
                    className="review-detail-tabs"
                    role="group"
                    aria-label="추출 결과 표시 방식"
                  >
                    <button
                      aria-pressed={view === "llm"}
                      onClick={() => setView("llm")}
                    >
                      LLM 결과
                    </button>
                    <button
                      aria-pressed={view === "stored"}
                      onClick={() => setView("stored")}
                    >
                      DB 저장 결과
                    </button>
                    <button
                      aria-pressed={view === "json"}
                      onClick={() => setView("json")}
                    >
                      JSON 원본
                    </button>
                  </div>
                </div>
                <p className="review-pane-note">
                  지시문 {detail.extraction.promptVersion}, 사전{" "}
                  {detail.extraction.dictVersion}
                </p>
                <div className="review-pane-content review-output-content">
                  {view === "json" ? (
                    <pre className="review-raw-json">
                      {detail.extraction.rawOutput === null
                        ? "이 실행에는 LLM 원본이 저장되지 않았습니다."
                        : JSON.stringify(detail.extraction.rawOutput, null, 2)}
                    </pre>
                  ) : view === "llm" ? (
                    <LlmResult value={detail.extraction.rawOutput} />
                  ) : detail.extraction.units.length ? (
                    detail.extraction.units.map((unit) => (
                      <section className="review-extracted-unit" key={unit.id}>
                        <h4>{unit.name}</h4>
                        <p>
                          {[
                            unit.job,
                            unit.career,
                            unit.years,
                            unit.isIt ? "" : "IT 직무 아님",
                          ]
                            .filter(Boolean)
                            .join(", ")}
                        </p>
                        {unit.items.length ? (
                          <ul>
                            {unit.items.map((item, i) => (
                              <li key={i}>
                                <span className="review-stored-category">
                                  {item.category}
                                </span>
                                <p>{item.text}</p>
                                {item.quote && (
                                  <details>
                                    <summary>근거 원문</summary>
                                    <blockquote>{item.quote}</blockquote>
                                  </details>
                                )}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="review-field-empty">
                            DB에 저장된 추출 항목 없음
                          </p>
                        )}
                      </section>
                    ))
                  ) : (
                    <p className="review-detail-empty">
                      저장된 모집 직무가 없습니다.
                    </p>
                  )}
                </div>
              </section>
            </div>
            {item!.feedback && !editing && (
              <p className="review-saved-feedback">
                <strong>최근 피드백, 처리 메모</strong>
                {item!.feedback}
              </p>
            )}
            {editing && (
              <label className="review-detail-feedback">
                재추출 피드백
                <textarea
                  autoFocus
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  minLength={5}
                  maxLength={2000}
                  disabled={busy}
                  placeholder="누락되거나 잘못 추출된 내용을 입력하세요."
                />
              </label>
            )}
          </>
        )}
        {actionError && (
          <p role="alert" className="career-error">
            {actionError}
          </p>
        )}
      </div>
      {detail && (
        <footer className="review-detail-footer">
          <p>
            {expired
              ? "마감 공고는 정상 등록과 재추출 요청을 할 수 없습니다."
              : "원문과 추출 내용을 확인한 뒤 처리해 주세요."}
          </p>
          <div>
            {canReview ? (
              <>
                <button
                  className="review-primary"
                  disabled={busy || !!expired}
                  onClick={() => void onDecision(item!, "APPROVE", "")}
                >
                  정상 등록
                </button>
                <button
                  disabled={busy}
                  onClick={() => void onDecision(item!, "PASS", "")}
                >
                  넘기기 (PASS)
                </button>
                {editing ? (
                  <>
                    <button disabled={busy} onClick={() => setEditing(false)}>
                      피드백 취소
                    </button>
                    <button
                      className="review-primary"
                      disabled={busy || !!expired || feedback.trim().length < 5}
                      onClick={() => void onDecision(item!, "RETRY", feedback)}
                    >
                      피드백 저장 및 재추출 요청
                    </button>
                  </>
                ) : (
                  <button
                    disabled={busy || !!expired}
                    onClick={() => setEditing(true)}
                  >
                    재추출 피드백
                  </button>
                )}
              </>
            ) : (
              <button
                disabled={busy || !detail.extraction.isCurrent}
                onClick={() => void onDecision(item!, "RESTORE", "")}
              >
                검토 대기로 되돌리기
              </button>
            )}
          </div>
        </footer>
      )}
    </section>
  );
}
