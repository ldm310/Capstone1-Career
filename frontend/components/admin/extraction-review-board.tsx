"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ListPagination } from "@/components/shared/list-pagination";
import { ReviewReason } from "./review-reason";

type Status = "OPEN" | "SKIPPED" | "RETRY_REQUESTED" | "RESOLVED";
type Item = {
  id: string;
  postingNo: string;
  site: string;
  company: string;
  title: string;
  sourceUrl: string;
  status: Status;
  feedback: string;
  updatedAt: string;
  revision: string;
  reviewReasons: Array<Record<string, unknown>>;
};
type List = {
  total: number;
  items: Item[];
  counts: Partial<Record<Status, number>>;
  nextOffset: number | null;
  lastPipelineAt: string | null;
};
const labels: Record<Status, string> = {
  OPEN: "검토 대기",
  SKIPPED: "제외 (넘김)",
  RETRY_REQUESTED: "재추출 요청",
  RESOLVED: "정상 확인",
};
function sourceLink(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
export function ExtractionReviewBoard() {
  const [data, setData] = useState<List>({
    total: 0,
    items: [],
    counts: {},
    nextOffset: null,
    lastPipelineAt: null,
  });
  const [status, setStatus] = useState<Status | "ALL">("OPEN");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const editor = useRef<HTMLTextAreaElement>(null);
  const version = useRef(0);
  const load = useCallback(async () => {
    const request = ++version.current;
    setLoading(true);
    try {
      const response = await fetch(
        "/api/admin/extraction-reviews?" +
          new URLSearchParams({ status, q: query, offset: String(offset) }),
        { cache: "no-store" },
      );
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error || "목록을 불러오지 못했습니다.");
      if (request === version.current) {
        const lastOffset = Math.max(0, (Math.ceil(body.total / 20) - 1) * 20);
        if (offset > lastOffset) {
          setOffset(lastOffset);
          return;
        }
        setData(body);
        setLoaded(true);
        setError("");
      }
    } catch (e) {
      if (request === version.current)
        setError(
          e instanceof Error ? e.message : "목록을 불러오지 못했습니다.",
        );
    } finally {
      if (request === version.current) setLoading(false);
    }
  }, [status, query, offset]);
  const invalidate = useCallback(() => {
    version.current++;
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load();
    });
    return () => {
      active = false;
      invalidate();
    };
  }, [load, invalidate]);
  useEffect(() => {
    if (selected) editor.current?.focus();
  }, [selected]);
  async function act(item: Item, action: "PASS" | "RETRY") {
    if (action === "RETRY" && feedback.trim().length < 5) {
      setError("재추출 피드백을 5자 이상 입력해 주세요.");
      return;
    }
    setBusy(item.id);
    setMessage("");
    setError("");
    try {
      const response = await fetch("/api/admin/extraction-reviews", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: item.id,
          revision: item.revision,
          action,
          feedback: action === "RETRY" ? feedback : "",
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "저장하지 못했습니다.");
      setSelected(null);
      setFeedback("");
      setMessage(
        action === "PASS"
          ? "공고를 제외로 저장했습니다."
          : "피드백과 재추출 요청을 저장했습니다.",
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <section className="extraction-review" aria-label="공고 추출 검토">
      <div className="review-summary">
        <div>
          <span>검토 대기</span>
          <strong>{loaded ? (data.counts.OPEN ?? 0) : "—"}</strong>
        </div>
        <div>
          <span>재추출 요청</span>
          <strong>{loaded ? (data.counts.RETRY_REQUESTED ?? 0) : "—"}</strong>
        </div>
        <div>
          <span>넘긴 공고</span>
          <strong>{loaded ? (data.counts.SKIPPED ?? 0) : "—"}</strong>
        </div>
      </div>
      <p className="review-policy">
        추출 결과의 모집 직무나 경력 조건 등에 확인이 필요한 공고입니다. 검토
        사유를 확인하고 넘기거나 재추출 피드백을 남겨 주세요.
      </p>
      {loaded && (
        <p className="review-worker">
          최근 추출 결과 저장:{" "}
          {data.lastPipelineAt
            ? new Date(data.lastPipelineAt).toLocaleString("ko-KR", {
                timeZone: "Asia/Seoul",
              })
            : "기록 없음"}
        </p>
      )}
      <form
        className="review-toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
          setOffset(0);
        }}
      >
        <label>
          처리 상태
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as Status | "ALL");
              setOffset(0);
              setSelected(null);
            }}
          >
            <option value="ALL">전체</option>
            {Object.entries(labels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="review-search">
          공고 검색
          <input
            value={search}
            maxLength={100}
            placeholder="회사명, 공고명, 공고번호"
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <button type="submit">검색</button>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading || !!busy}
        >
          새로고침
        </button>
      </form>
      {error && (
        <p role="alert" className="career-error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="review-success">
          {message}
        </p>
      )}
      <div className="review-list" aria-busy={loading}>
        {loading ? (
          <p className="review-empty" role="status">
            목록을 불러오는 중입니다.
          </p>
        ) : error && !loaded ? (
          <div className="review-empty">
            <h2>목록 연결 확인이 필요합니다</h2>
            <p>잠시 후 새로고침해 주세요.</p>
          </div>
        ) : data.items.length === 0 ? (
          <div className="review-empty">
            <h2>해당 공고가 없습니다</h2>
            <p>
              현재 추출 결과에 검토 필요 표시가 있는 공고가 여기에 표시됩니다.
            </p>
          </div>
        ) : (
          data.items.map((item) => {
            const locked = !!busy || item.status !== "OPEN";
            const link = sourceLink(item.sourceUrl);
            return (
              <article key={item.id} className="review-row">
                <div className="review-row-main">
                  <div className="review-posting">
                    <span className="review-company">
                      {item.company || "회사 정보 없음"}
                    </span>
                    <h2>{item.title || "공고명 없음"}</h2>
                    <span className="review-posting-meta">
                      {item.site} / {item.postingNo}
                    </span>
                    {link && (
                      <a href={link} target="_blank" rel="noopener noreferrer">
                        공고 원문
                      </a>
                    )}
                  </div>
                  <div className="review-failure">
                    <span
                      className={
                        "review-state state-" + item.status.toLowerCase()
                      }
                    >
                      {labels[item.status]}
                    </span>
                    <strong>
                      검토 사유 {item.reviewReasons?.length || 1}개
                    </strong>
                    <span>추출 결과 검토</span>
                    {item.reviewReasons?.length ? (
                      <ul className="review-reasons">
                        {item.reviewReasons.map((reason, index) => (
                          <li key={index}>
                            <ReviewReason reason={reason} />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>검토 사유 확인 필요</p>
                    )}
                    <time dateTime={item.updatedAt}>
                      {new Date(item.updatedAt).toLocaleString("ko-KR", {
                        timeZone: "Asia/Seoul",
                      })}
                    </time>
                  </div>
                  <div className="review-row-actions">
                    <button
                      type="button"
                      onClick={() => void act(item, "PASS")}
                      disabled={locked}
                    >
                      넘기기 (PASS)
                    </button>
                    <button
                      type="button"
                      className="review-primary"
                      onClick={() => {
                        setSelected(item.id);
                        setFeedback(item.feedback);
                        setError("");
                      }}
                      disabled={locked}
                    >
                      재추출 피드백
                    </button>
                  </div>
                </div>
                {item.feedback && selected !== item.id && (
                  <p className="review-saved-feedback">
                    <strong>최근 피드백</strong>
                    {item.feedback}
                  </p>
                )}
                {selected === item.id && (
                  <form
                    className="review-feedback"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void act(item, "RETRY");
                    }}
                  >
                    <label htmlFor={"feedback-" + item.id}>
                      역량 재추출 피드백
                    </label>
                    <textarea
                      id={"feedback-" + item.id}
                      ref={editor}
                      required
                      minLength={5}
                      maxLength={2000}
                      value={feedback}
                      onChange={(event) => setFeedback(event.target.value)}
                      placeholder="예: 이미지 하단의 자격요건이 누락됐습니다. 해당 영역의 OCR 결과를 확인해 주세요."
                    />
                    <p>
                      추출 결과에 피드백과 재추출 요청을 저장합니다.
                      파이프라인은 다음 실행에서 처리 대상 공고의 피드백을
                      읽습니다.
                    </p>
                    <div>
                      <button
                        type="button"
                        onClick={() => setSelected(null)}
                        disabled={!!busy}
                      >
                        취소
                      </button>
                      <button
                        type="submit"
                        className="review-primary"
                        disabled={!!busy || feedback.trim().length < 5}
                      >
                        {busy === item.id
                          ? "저장 중…"
                          : "피드백 저장 및 재추출 요청"}
                      </button>
                    </div>
                  </form>
                )}
              </article>
            );
          })
        )}
      </div>
      {loaded && !error && !loading && (
        <ListPagination
          total={data.total}
          offset={offset}
          pageSize={20}
          loading={!!busy}
          label="공고 검토 페이지"
          onChange={(next) => {
            setOffset(next);
            setSelected(null);
            document
              .querySelector(".review-toolbar")
              ?.scrollIntoView({ block: "start" });
          }}
        />
      )}
    </section>
  );
}
