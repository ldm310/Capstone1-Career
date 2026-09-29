"use client";
import type { PanelProps } from "./types";
import { ExternalLink, Upload, GitBranch } from "lucide-react";
import { evidenceLabel } from "./helpers";
export function SourcesPanel({
  busy,
  request,
  findings,
}: Pick<PanelProps, "busy" | "request" | "findings">) {
  return (
    <>
      <section className="career-panel">
        <h2>지금까지 해온 것을 알려주세요</h2>
        <p>
          자료 하나로 시작할 수 있어요. 분석 후 찾은 기술과 근거를 확인해
          주세요. 기술 언급만으로 수준을 확정하지 않으며, 자료는 나중에 더
          추가할 수 있어요.
        </p>
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
            <h3>
              <GitBranch size={18} /> GitHub 공개 저장소
            </h3>
            <label>
              저장소 URL
              <input
                name="url"
                type="url"
                required
                placeholder="https://github.com/owner/repository"
              />
            </label>
            <small>
              최대 20개 소스·설정 파일을 읽고 커밋·파일·행 링크를 남깁니다.
            </small>
            <button disabled={busy}>프로젝트 분석하기</button>
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
            <h3>
              <Upload size={18} /> PDF · Markdown
            </h3>
            <label>
              자료 종류
              <select name="source">
                <option value="cv">이력서·경력 문서</option>
                <option value="notion">학습 노트·프로젝트 설명</option>
              </select>
            </label>
            <label>
              파일 선택
              <input required type="file" name="file" accept=".pdf,.md" />
            </label>
            <small>
              PDF(이력서·포트폴리오) 또는 Markdown(.md, 학습 노트·프로젝트
              설명), 10MB 이하. Notion 자료는 Markdown으로 내보내서 올려주세요.
              기존 자료는 그대로 보관돼요.
            </small>
            <button disabled={busy}>파일 저장하고 분석하기</button>
          </form>
        </div>
      </section>
      <section className="career-panel">
        <h2>발견한 근거 · {findings.length}개</h2>
        {!findings.length && (
          <p>아직 근거가 없습니다. 자료 분석부터 시작하세요.</p>
        )}
        {findings.map((f) => (
          <article className="finding" key={f.id}>
            <span className="live-label">
              {f.skill} · {evidenceLabel(f)}
            </span>
            <h3>{f.title}</h3>
            <pre>{f.quote}</pre>
            <a href={f.url} target="_blank" rel="noreferrer">
              원문에서 확인 <ExternalLink size={13} />
            </a>
          </article>
        ))}
      </section>
    </>
  );
}
