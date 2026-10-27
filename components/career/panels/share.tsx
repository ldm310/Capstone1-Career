"use client";
import type { PanelProps } from "./types";
export function SharePanel({
  busy,
  request,
  setNotice,
  findings,
  shares,
  selected,
  setSelected,
  setShares,
}: Pick<
  PanelProps,
  | "busy"
  | "request"
  | "setNotice"
  | "findings"
  | "shares"
  | "selected"
  | "setSelected"
  | "setShares"
>) {
  return (
    <section className="career-panel">
      <h2>포트폴리오 공유</h2>
      <p>선택한 근거만 공개돼요. 이력서 원본은 공개되지 않아요.</p>
      {findings.map((f) => (
        <label className="share-choice" key={f.id}>
          <input
            type="checkbox"
            checked={selected.includes(f.id)}
            onChange={() =>
              setSelected((s) =>
                s.includes(f.id) ? s.filter((x) => x !== f.id) : [...s, f.id],
              )
            }
          />
          <span>
            <strong>
              {f.skill} - {f.title}
            </strong>
            <pre>{f.quote}</pre>
          </span>
        </label>
      ))}
      {!findings.length && <p>자료를 분석하면 근거를 고를 수 있어요.</p>}
      <button
        disabled={busy || !selected.length}
        onClick={async () => {
          const data = await request("/api/share", { ids: selected });
          if (data?.url) {
            setShares((s) => [data.url!.split("/").pop()!, ...s]);
            setNotice("공유 링크를 만들었어요.");
          }
        }}
      >
        공유 링크 만들기 ({selected.length})
      </button>
      <h3>공개 중인 링크</h3>
      {shares.map((token) => (
        <div className="career-row" key={token}>
          <a href={`/share/${token}`} target="_blank" rel="noreferrer">
            포트폴리오 열기 ↗
          </a>
          <button
            onClick={async () => {
              await navigator.clipboard.writeText(
                `${location.origin}/share/${token}`,
              );
              setNotice("링크를 복사했어요.");
            }}
          >
            복사
          </button>
          <button
            disabled={busy}
            onClick={async () => {
              if (await request("/api/share", { token }, "DELETE"))
                setShares((s) => s.filter((t) => t !== token));
            }}
          >
            공유 중단
          </button>
        </div>
      ))}
      <small>링크는 만든 시점의 사본이에요.</small>
    </section>
  );
}
