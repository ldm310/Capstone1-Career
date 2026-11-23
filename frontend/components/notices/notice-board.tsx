"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

interface Notice {
  id: string;
  title: string;
  content: string;
  authorName: string;
  pinned: boolean;
  createdAt: string;
  updatedAt: string;
}
async function readNotices(offset = 0, signal?: AbortSignal) {
  const response = await fetch(`/api/notices?offset=${offset}`, {
      cache: "no-store",
      signal,
    }),
    data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data as {
    notices: Notice[];
    canManage: boolean;
    nextOffset: number | null;
  };
}
export function NoticeBoard() {
  const [notices, setNotices] = useState<Notice[]>([]),
    [canManage, setCanManage] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [selected, setSelected] = useState<Notice | null>(null),
    [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(false),
    [next, setNext] = useState<number | null>(null);
  const [title, setTitle] = useState(""),
    [content, setContent] = useState(""),
    [pinned, setPinned] = useState(false),
    [remove, setRemove] = useState(false);
  async function load(offset = 0) {
    try {
      const data = await readNotices(offset);
      setNotices((items) =>
        offset ? [...items, ...data.notices] : data.notices,
      );
      setCanManage(data.canManage);
      setNext(data.nextOffset);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "공지를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    void readNotices(0, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setNotices(data.notices);
          setCanManage(data.canManage);
          setNext(data.nextOffset);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setError(
            error instanceof Error
              ? error.message
              : "공지를 불러오지 못했습니다.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);
  function edit(notice: Notice | null) {
    setSelected(notice);
    setTitle(notice?.title || "");
    setContent(notice?.content || "");
    setPinned(notice?.pinned || false);
    setEditing(true);
    setRemove(false);
    setError("");
  }
  async function save(method: "POST" | "PATCH" | "DELETE") {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/notices", {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: selected?.id, title, content, pinned }),
        }),
        data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setEditing(false);
      setSelected(null);
      setRemove(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="notice-board" aria-label="공지사항 게시판">
      <div className="notice-toolbar">
        <p>서비스 소식과 이용 안내</p>
        {canManage && !editing && (
          <button className="notice-primary" onClick={() => edit(null)}>
            공지 작성
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="notice-error">
          {error} <button onClick={() => void load()}>다시 확인</button>
        </p>
      )}
      {editing ? (
        <form
          className="notice-editor"
          onSubmit={(e) => {
            e.preventDefault();
            void save(selected ? "PATCH" : "POST");
          }}
        >
          <h2>{selected ? "공지 수정" : "공지 작성"}</h2>
          <label>
            제목
            <input
              required
              maxLength={120}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={busy}
            />
          </label>
          <label>
            내용
            <textarea
              required
              maxLength={12000}
              rows={12}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={busy}
            />
          </label>
          <label className="notice-check">
            <input
              type="checkbox"
              checked={pinned}
              onChange={(e) => setPinned(e.target.checked)}
              disabled={busy}
            />
            목록 상단에 고정
          </label>
          <div className="notice-actions">
            <button type="submit" className="notice-primary" disabled={busy}>
              {busy ? "저장 중" : "저장"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(false)}
            >
              취소
            </button>
          </div>
        </form>
      ) : selected ? (
        <article className="notice-detail">
          <button
            className="notice-back"
            onClick={() => {
              setSelected(null);
              setRemove(false);
            }}
          >
            공지 목록
          </button>
          <h2>{selected.title}</h2>
          <p className="notice-meta">
            {selected.authorName},{" "}
            {new Date(selected.createdAt).toLocaleDateString("ko-KR")}
          </p>
          <div className="notice-content">{selected.content}</div>
          {canManage && (
            <div className="notice-actions">
              <button onClick={() => edit(selected)}>수정</button>
              <button onClick={() => setRemove(true)}>삭제</button>
              {remove && (
                <>
                  <span>이 공지를 삭제할까요?</span>
                  <button disabled={busy} onClick={() => void save("DELETE")}>
                    삭제 확인
                  </button>
                  <button onClick={() => setRemove(false)}>취소</button>
                </>
              )}
            </div>
          )}
        </article>
      ) : (
        <>
          {loading ? (
            <p role="status">공지사항을 불러오는 중입니다.</p>
          ) : !notices.length && !error ? (
            <p className="notice-empty">등록된 공지사항이 없습니다.</p>
          ) : (
            <ul className="notice-list">
              {notices.map((notice) => (
                <li key={notice.id}>
                  <button
                    onClick={() => {
                      setSelected(notice);
                      setRemove(false);
                    }}
                  >
                    <span>
                      {notice.pinned && <small>공지</small>}
                      {notice.title}
                    </span>
                    <time dateTime={notice.createdAt}>
                      {new Date(notice.createdAt).toLocaleDateString("ko-KR")}
                    </time>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {next !== null && (
            <button className="notice-more" onClick={() => void load(next)}>
              더 보기
            </button>
          )}
          {!canManage && (
            <p className="notice-meta">
              공지사항은 관리자가 작성합니다.{" "}
              <Link href="/sign-in">로그인</Link>
            </p>
          )}
        </>
      )}
    </section>
  );
}
