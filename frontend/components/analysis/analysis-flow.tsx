"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, LoaderCircle, Plus, X } from "lucide-react";

type Source = {
  id: string;
  kind: "github" | "pdf";
  name: string;
  url?: string;
  file?: File;
  state: "ready" | "running" | "done" | "failed";
  error?: string;
};

export function AnalysisFlow() {
  const [access, setAccess] = useState<"checking" | "member" | "visitor">(
    "checking",
  );
  useEffect(() => {
    let active = true;
    fetch("/api/account", { cache: "no-store" })
      .then(async (response) => {
        const account = await response.json();
        if (active)
          setAccess(
            response.ok && account.user && account.guest === false
              ? "member"
              : "visitor",
          );
      })
      .catch(() => {
        if (active) setAccess("visitor");
      });
    return () => {
      active = false;
    };
  }, []);
  const [sources, setSources] = useState<Source[]>([]);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const [preview, setPreview] = useState(false);
  const lock = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const done = sources.filter((source) => source.state === "done").length;

  function addGithub() {
    try {
      const parsed = new URL(url.trim());
      if (
        parsed.protocol !== "https:" ||
        parsed.hostname !== "github.com" ||
        parsed.username ||
        parsed.password ||
        parsed.port ||
        !/^\/[\w.-]+\/[\w.-]+\/?$/.test(parsed.pathname)
      )
        throw new Error();
      const normalized = `https://github.com${parsed.pathname.replace(/\/$/, "").replace(/\.git$/, "")}`;
      if (
        sources.some(
          (source) => source.url?.toLowerCase() === normalized.toLowerCase(),
        )
      ) {
        setError("이미 추가한 GitHub 저장소예요.");
        return;
      }
      setSources((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          kind: "github",
          name: normalized.replace("https://github.com/", ""),
          url: normalized,
          state: "ready",
        },
      ]);
      setUrl("");
      setError("");
    } catch {
      setError(
        "공개 GitHub 저장소 링크를 입력해 주세요. 예: https://github.com/owner/repository",
      );
    }
  }

  function addFiles(files: FileList | null) {
    if (!files) return;
    const added: Source[] = [];
    const errors: string[] = [];
    for (const file of Array.from(files)) {
      if (
        !/\.pdf$/i.test(file.name) ||
        (file.type &&
          !["application/pdf", "application/octet-stream"].includes(file.type))
      ) {
        errors.push(`${file.name}: PDF 파일만 추가할 수 있어요.`);
      } else if (file.size === 0 || file.size > 10_000_000) {
        errors.push(
          `${file.name}: 비어 있지 않은 10MB 이하 파일을 선택해 주세요.`,
        );
      } else if (
        [...sources, ...added].some(
          (source) =>
            source.file?.name === file.name &&
            source.file.size === file.size &&
            source.file.lastModified === file.lastModified,
        )
      ) {
        errors.push(`${file.name}: 이미 추가한 파일이에요.`);
      } else {
        added.push({
          id: crypto.randomUUID(),
          kind: "pdf",
          name: file.name,
          file,
          state: "ready",
        });
      }
    }
    setSources((items) => [...items, ...added]);
    setError(errors.join(" "));
  }

  async function analyze() {
    if (lock.current || !sources.length || access !== "member") return;
    lock.current = true;
    setBusy(true);
    setError("");
    let succeeded = sources.filter((source) => source.state === "done").length;
    try {
      const accountResponse = await fetch("/api/account", {
        cache: "no-store",
      });
      const account = await accountResponse.json();
      if (!accountResponse.ok || !account.user || account.guest !== false) {
        setAccess("visitor");
        throw new Error("로그인 후 역량 분석을 시작해 주세요.");
      }
      const session = await fetch("/api/career");
      if (!session.ok)
        throw new Error("분석 공간을 열지 못했어요. 다시 시도해 주세요.");
      for (const source of sources.filter((item) => item.state !== "done")) {
        setSources((items) =>
          items.map((item) =>
            item.id === source.id
              ? { ...item, state: "running", error: undefined }
              : item,
          ),
        );
        try {
          const body = source.kind === "pdf" ? new FormData() : null;
          if (body && source.file) {
            body.set("file", source.file);
            body.set("source", "cv");
          }
          const response = await fetch(
            source.kind === "pdf"
              ? "/api/documents"
              : preview
                ? "/api/analysis-preview"
                : "/api/analyze",
            {
              method: "POST",
              ...(body
                ? { body }
                : {
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ kind: "github", url: source.url }),
                  }),
            },
          );
          const data = await response.json();
          if (!response.ok || !data.workspace)
            throw new Error(data.error || "자료를 분석하지 못했어요.");
          succeeded++;
          setSources((items) =>
            items.map((item) =>
              item.id === source.id ? { ...item, state: "done" } : item,
            ),
          );
        } catch (failure) {
          setSources((items) =>
            items.map((item) =>
              item.id === source.id
                ? {
                    ...item,
                    state: "failed",
                    error:
                      failure instanceof Error
                        ? failure.message
                        : "다시 시도해 주세요.",
                  }
                : item,
            ),
          );
        }
      }
      if (succeeded === sources.length) {
        setComplete(true);
        requestAnimationFrame(() => {
          heading.current?.focus({ preventScroll: true });
          window.scrollTo({ top: 0, behavior: "auto" });
        });
      } else
        setError(
          "일부 자료를 분석하지 못했어요. 오류를 확인하고 다시 시도해 주세요. 완료된 자료는 다시 보내지 않아요.",
        );
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "연결을 확인해 주세요.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  if (complete)
    return (
      <section className="analysis-flow analysis-complete">
        <p className="analysis-eyebrow">ANALYSIS</p>
        <h2 ref={heading} tabIndex={-1}>
          분석 완료
        </h2>
        <p>분석 결과는 각 채용공고의 역량 비교에서 확인할 수 있습니다.</p>
        <div className="analysis-complete-summary">
          <span>자료 {done}개 분석 완료</span>
        </div>
        <Link className="analysis-primary" href="/jobs">
          채용공고에서 내 역량 확인하기
        </Link>
        <button
          className="analysis-text-button"
          onClick={() => {
            setComplete(false);
            setSources([]);
          }}
        >
          자료 더 추가하기
        </button>
      </section>
    );

  return (
    <section
      className="analysis-flow"
      aria-labelledby="analysis-start-title"
      aria-busy={busy}
    >
      <ol className="analysis-steps" aria-label="분석 진행 순서">
        <li aria-current={busy ? undefined : "step"}>
          1 <span>자료 추가</span>
        </li>
        <li aria-current={busy ? "step" : undefined}>
          2 <span>분석</span>
        </li>
        <li>
          3 <span>공고 비교</span>
        </li>
      </ol>
      <h2 id="analysis-start-title">{busy ? "자료 분석 중" : "분석 자료"}</h2>
      <p className="analysis-intro">
        GitHub 링크 또는 PDF 이력서를 1개 이상 등록하세요.
      </p>
      <aside
        className="analysis-template"
        aria-labelledby="resume-template-title"
      >
        <div>
          <h3 id="resume-template-title">Career 이력서 양식</h3>
          <p>Word 양식에 작성한 뒤 PDF로 저장해 업로드하세요.</p>
          <div className="analysis-template-links">
            <a href="/downloads/career-resume-template.docx" download>
              Career 이력서 양식 다운로드, Word
            </a>
            <a href="/downloads/career-resume-template.pdf" download>
              PDF 양식 받기
            </a>
          </div>
          <small>양식은 로그인 없이도 받을 수 있어요.</small>
        </div>
      </aside>
      {access === "checking" && (
        <p role="status" className="analysis-login-note">
          로그인 상태를 확인하고 있어요.
        </p>
      )}
      {access === "visitor" && (
        <aside className="analysis-login-note">
          <h3>회원 전용 분석</h3>
          <p>
            채용공고는 로그인 없이 볼 수 있어요. 내 자료를 분석하려면 로그인해
            주세요.
          </p>
          <Link href="/sign-in">로그인, 회원가입</Link>
        </aside>
      )}
      <fieldset
        className="analysis-inputs"
        disabled={busy || access !== "member"}
      >
        <legend className="sr-only">분석할 자료 추가</legend>
        <form
          className="analysis-source-block"
          onSubmit={(event) => {
            event.preventDefault();
            addGithub();
          }}
        >
          <div className="analysis-source-heading">
            <div>
              <h3>GitHub 링크</h3>
              <p>공개 저장소 주소를 등록하세요.</p>
            </div>
          </div>
          <label htmlFor="analysis-github-url" className="sr-only">
            공개 GitHub 저장소 URL
          </label>
          <div className="analysis-url-row">
            <input
              id="analysis-github-url"
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://github.com/owner/repository"
            />
            <button type="submit" disabled={!url.trim()}>
              <Plus size={18} aria-hidden="true" />
              링크 추가
            </button>
          </div>
          <div className="analysis-preview-controls">
            <button
              type="button"
              onClick={() => {
                setUrl("https://github.com/career-demo/order-service");
                setPreview(true);
              }}
            >
              예시 링크 사용
            </button>
            <label>
              <input
                type="checkbox"
                checked={preview}
                onChange={(event) => setPreview(event.target.checked)}
              />
              GitHub 분석 미리보기
            </label>
          </div>
        </form>
        <div className="analysis-source-block">
          <div className="analysis-source-heading">
            <div>
              <h3>PDF 이력서</h3>
              <p>PDF만 등록할 수 있습니다. 파일당 최대 10MB입니다.</p>
            </div>
          </div>
          <label className="analysis-file-picker">
            <input
              type="file"
              accept=".pdf,application/pdf"
              multiple
              aria-label="PDF 이력서 추가"
              onChange={(event) => {
                addFiles(event.target.files);
                event.target.value = "";
              }}
            />
            <strong>PDF 파일 추가</strong>
            <span>여러 파일 선택 가능, 파일당 10MB 이하</span>
          </label>
        </div>
      </fieldset>
      <div className="analysis-selected-heading">
        <h3>
          추가한 자료 <span>{sources.length}</span>
        </h3>
        <span>1개 이상이면 시작할 수 있어요</span>
      </div>
      {sources.length ? (
        <ul className="analysis-source-list">
          {sources.map((source) => (
            <li key={source.id}>
              <span className="analysis-source-kind">
                {source.kind === "github" ? "GitHub" : "PDF"}
              </span>
              <div>
                <strong>{source.name}</strong>
                <small>
                  {source.state === "done"
                    ? "분석 완료"
                    : source.state === "running"
                      ? "분석 중…"
                      : source.error ||
                        (source.kind === "github"
                          ? "공개 GitHub 저장소"
                          : `${((source.file?.size ?? 0) / 1_000_000).toFixed(1)}MB,  PDF`)}
                </small>
              </div>
              {source.state === "done" ? (
                <Check size={18} aria-label="완료" />
              ) : source.state === "running" ? (
                <LoaderCircle
                  className="analysis-spinner"
                  size={18}
                  aria-label="처리 중"
                />
              ) : (
                <button
                  disabled={busy}
                  aria-label={`${source.name} 제거`}
                  onClick={() =>
                    setSources((items) =>
                      items.filter((item) => item.id !== source.id),
                    )
                  }
                >
                  <X size={18} />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="analysis-empty">등록한 자료가 없습니다.</p>
      )}
      {error && (
        <p className="analysis-error" role="alert">
          {error}
        </p>
      )}
      <div className="analysis-progress" role="status">
        {busy && `${sources.length}개 중 ${done}개 분석 완료`}
      </div>
      <button
        className="analysis-primary"
        disabled={
          !sources.length || busy || !!url.trim() || access !== "member"
        }
        onClick={() => void analyze()}
      >
        {busy ? (
          <>
            <LoaderCircle
              className="analysis-spinner"
              size={19}
              aria-hidden="true"
            />
            분석 중이에요
          </>
        ) : (
          <>
            {sources.some((source) => source.state === "failed")
              ? "실패한 자료 다시 분석하기"
              : "분석 시작하기"}
          </>
        )}
      </button>
      <p className="analysis-bottom-note">
        {url.trim()
          ? "입력한 링크를 추가하거나 지운 뒤 시작해 주세요."
          : "분석한 역량은 각 채용공고의 비교 화면에서 확인해요."}
      </p>
    </section>
  );
}
