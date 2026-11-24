"use client";
import type { PanelProps } from "./types";
import { ExternalLink } from "lucide-react";
import { evidenceLabel } from "./helpers";
export function SourcesPanel({
  busy,
  request,
  findings,
}: Pick<PanelProps, "busy" | "request" | "findings">) {
  return (
    <>
      <section className="career-panel">
        <h2>자료 추가</h2>
        <p>자료 하나로 시작할 수 있어요.</p>
        <div className="career-two">
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              await request("/api/analyze", {
                kind: "github",
                url: form.get("url"),
              });
            }}
          >
            <h3>GitHub 저장소</h3>
            <label>
              저장소 URL
              <input
                name="url"
                type="url"
                required
                placeholder="https://github.com/owner/repository"
              />
            </label>
            <small>공개 저장소, 파일 최대 20개</small>
            <button disabled={busy}>분석하기</button>
          </form>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const element = e.currentTarget;
              const form = new FormData(element);
              const result = await request("/api/documents", form);
              if (result) element.reset();
            }}
          >
            <h3>PDF, Markdown</h3>
            <label>
              자료 종류
              <select name="source">
                <option value="cv">이력서, 경력 문서</option>
                <option value="notion">학습 노트, 프로젝트 설명</option>
              </select>
            </label>
            <label>
              파일 선택
              <input required type="file" name="file" accept=".pdf,.md" />
            </label>
            <small>10MB 이하, Notion은 Markdown으로 내보내기</small>
            <button disabled={busy}>저장하고 분석하기</button>
          </form>
        </div>
      </section>
      <section className="career-panel">
        <h2>발견한 근거 {findings.length}개</h2>
        {!findings.length && <p>아직 근거가 없어요.</p>}
        {findings.map((f) => (
          <article className="finding" key={f.id}>
            <span className="live-label">
              {f.skill} - {evidenceLabel(f)}
            </span>
            <h3>{f.title}</h3>
            <pre>{f.quote}</pre>
            <a href={f.url} target="_blank" rel="noreferrer">
              원문 보기 <ExternalLink size={13} />
            </a>
          </article>
        ))}
      </section>
    </>
  );
}
