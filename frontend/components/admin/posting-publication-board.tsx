"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ListPagination } from "@/components/shared/list-pagination";
import type {
  PublicationItem,
  PublicationStatus,
} from "@/lib/server/posting-publication";

const labels: Record<PublicationStatus, string> = {
  PUBLISHED: "노출 중",
  HIDDEN: "숨긴 공고",
  FILTERED: "노출 제외",
  CLOSED: "마감",
};
export function PostingPublicationBoard() {
  const [status, setStatus] = useState<PublicationStatus>("PUBLISHED"),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [offset, setOffset] = useState(0),
    [retry, setRetry] = useState(0);
  const [data, setData] = useState<{
    total: number;
    items: PublicationItem[];
    counts: Partial<Record<PublicationStatus, number>>;
  }>({ total: 0, items: [], counts: {} });
  const [busy, setBusy] = useState(true),
    [saving, setSaving] = useState<string | null>(null),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      setBusy(true);
      setError("");
      try {
        const r = await fetch(
          `/api/admin/postings?status=${status}&q=${encodeURIComponent(query)}&offset=${offset}`,
          { signal: controller.signal, cache: "no-store" },
        );
        const next = await r.json();
        if (!r.ok) throw new Error(next.error);
        const last = Math.max(0, (Math.ceil(next.total / 20) - 1) * 20);
        if (offset > last) {
          setOffset(last);
          return;
        }
        if (!controller.signal.aborted) setData(next);
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "조회 오류");
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    })();
    return () => controller.abort();
  }, [status, query, offset, retry]);
  async function change(item: PublicationItem) {
    setSaving(item.id);
    setError("");
    setMessage("");
    try {
      const r = await fetch("/api/admin/postings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: item.id,
          revision: item.revision,
          hidden: !item.hidden,
        }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error);
      setMessage(
        item.hidden ? "공고를 다시 올렸습니다." : "공고를 숨겼습니다.",
      );
      setRetry((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 오류");
    } finally {
      setSaving(null);
    }
  }
  return (
    <section className="extraction-review" aria-label="공고 노출 관리">
      <h2>공고 노출 관리</h2>
      <p className="review-policy">
        백엔드 또는 데이터 엔지니어 직무와 본문이 추출된 진행 공고만 웹에
        노출됩니다. 숨김은 재추출 후에도 유지됩니다.
      </p>
      <div
        className="publication-tabs"
        role="group"
        aria-label="공고 노출 상태"
      >
        {(Object.keys(labels) as PublicationStatus[]).map((key) => (
          <button
            key={key}
            aria-pressed={key === status}
            disabled={saving !== null}
            onClick={() => {
              setStatus(key);
              setOffset(0);
              setMessage("");
            }}
          >
            {labels[key]} {data.counts[key] ?? 0}
          </button>
        ))}
      </div>
      <form
        className="review-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search.trim());
          setOffset(0);
        }}
      >
        <label className="review-search">
          회사, 공고명, 공고 번호
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            maxLength={100}
          />
        </label>
        <button disabled={busy || saving !== null}>검색</button>
      </form>
      {message && (
        <p className="review-success" role="status">
          {message}
        </p>
      )}
      {error ? (
        <div role="alert">
          <p>{error}</p>
          <button onClick={() => setRetry((v) => v + 1)}>새로고침</button>
        </div>
      ) : (
        <>
          <div className="publication-list" aria-busy={busy}>
            {!busy &&
              data.items.map((item) => (
                <article key={item.id} className="career-panel publication-row">
                  <div>
                    <strong>{item.company}</strong>
                    <h3>{item.title}</h3>
                    <p>
                      {item.site}, {item.postingNo} / 마감일{" "}
                      {item.deadline?.slice(0, 10) || "미지정"}
                    </p>
                    <div className="publication-links">
                      {item.state === "PUBLISHED" && (
                        <Link
                          href={`/jobs?job=${encodeURIComponent(`be:${item.id}`)}&view=posting`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          사이트에서 보기
                        </Link>
                      )}
                      {item.sourceUrl && (
                        <a
                          href={item.sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          공고 원문
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="publication-actions">
                    <div className="publication-action-line">
                      <span className="publication-state">
                        {labels[item.state]}
                      </span>
                      {item.state === "PUBLISHED" || item.hidden ? (
                        <button
                          disabled={
                            busy ||
                            saving !== null ||
                            (item.hidden && !item.eligible)
                          }
                          onClick={() => void change(item)}
                        >
                          {saving === item.id
                            ? "저장 중…"
                            : item.hidden
                              ? "다시 올리기"
                              : "숨기기"}
                        </button>
                      ) : null}
                    </div>
                    {item.hidden && !item.eligible && (
                      <p>
                        마감, 검토 제외 또는 추출 조건 미충족으로 다시 올릴 수
                        없습니다.
                      </p>
                    )}
                    {item.state === "FILTERED" && (
                      <p>
                        대상 직무 또는 추출 본문이 없거나 검토에서 제외된
                        공고입니다.
                      </p>
                    )}
                  </div>
                </article>
              ))}
            {busy && <p role="status">불러오는 중…</p>}
            {!busy && !data.total && (
              <p className="review-empty">해당 상태의 공고가 없습니다.</p>
            )}
          </div>
          <ListPagination
            total={data.total}
            offset={offset}
            pageSize={20}
            loading={busy || saving !== null}
            label="공고 노출 관리 페이지"
            onChange={setOffset}
          />
        </>
      )}
    </section>
  );
}
