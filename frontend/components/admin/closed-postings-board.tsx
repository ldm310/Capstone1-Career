"use client";
import { useEffect, useState } from "react";
import { ListPagination } from "@/components/shared/list-pagination";
type Item = {
  id: string;
  company: string;
  title: string;
  site: string;
  postingNo: string;
  deadline: string | null;
  reason: string;
  sourceUrl: string;
};
export function ClosedPostingsBoard() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; items: Item[] }>({
    total: 0,
    items: [],
  });
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      setBusy(true);
      setError("");
      try {
        const response = await fetch(
          `/api/admin/closed-postings?q=${encodeURIComponent(query)}&offset=${offset}`,
          { signal: controller.signal },
        );
        const next = await response.json();
        if (!response.ok) throw new Error(next.error);
        const last = Math.max(0, (Math.ceil(next.total / 20) - 1) * 20);
        if (offset > last) {
          setOffset(last);
          return;
        }
        setData(next);
      } catch (error) {
        if (!controller.signal.aborted)
          setError(error instanceof Error ? error.message : "조회 오류");
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    })();
    return () => controller.abort();
  }, [query, offset, retry]);
  return (
    <section className="extraction-review" aria-label="마감 공고 관리">
      <h2>마감 공고</h2>
      <p className="review-policy">
        한국 시간 기준 마감일이 지났거나 원문에서 마감된 공고입니다. 일반 공고
        목록에서 제외되며 기록은 보관됩니다.
      </p>
      <form
        className="review-toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
          setOffset(0);
        }}
      >
        <label className="review-search">
          회사, 공고명, 공고 번호
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            maxLength={100}
          />
        </label>
        <button type="submit">검색</button>
      </form>
      {error ? (
        <div role="alert">
          <p>{error}</p>
          <button onClick={() => setRetry((v) => v + 1)}>다시 시도</button>
        </div>
      ) : (
        <>
          <div className="closed-postings-list" aria-busy={busy}>
            {data.items.map((item) => (
              <article key={item.id} className="career-panel">
                <div>
                  <strong>{item.company}</strong>
                  <h3>{item.title}</h3>
                  <p>
                    {item.site}, {item.postingNo}
                  </p>
                </div>
                <div>
                  <span>{item.reason}</span>
                  <p>마감일 {item.deadline?.slice(0, 10) || "미정"}</p>
                  {item.sourceUrl && (
                    <a href={item.sourceUrl} target="_blank" rel="noreferrer">
                      공고 원문
                    </a>
                  )}
                </div>
              </article>
            ))}
            {!busy && !data.total && <p>마감 공고가 없습니다.</p>}
            {busy && <p role="status">불러오는 중…</p>}
          </div>
          <ListPagination
            total={data.total}
            offset={offset}
            pageSize={20}
            loading={busy}
            label="마감 공고 페이지"
            onChange={setOffset}
          />
        </>
      )}
    </section>
  );
}
