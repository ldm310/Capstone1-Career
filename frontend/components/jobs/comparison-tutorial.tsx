"use client";
import { useState } from "react";
import Link from "next/link";
import { SavedLevelRadar } from "./saved-level-radar";
import { experienceJob, experienceLevels } from "@/mock/posting-experience";

export function ComparisonTutorial() {
  const [started, setStarted] = useState(false);
  return (
    <div className="comparison-tutorial">
      <section className="career-panel comparison-tutorial-intro">
        <span className="comparison-tutorial-label">이용 안내</span>
        <h2>공고별 역량 비교</h2>
        <p>
          로그인하면 GitHub 링크와 PDF 이력서를 등록하고, 각 채용 공고에서 내
          역량을 비교할 수 있습니다.
        </p>
        <ol className="comparison-tutorial-steps">
          <li>
            <strong>01</strong>
            <span>로그인</span>
          </li>
          <li>
            <strong>02</strong>
            <span>GitHub, PDF 등록</span>
          </li>
          <li>
            <strong>03</strong>
            <span>공고별 역량 비교</span>
          </li>
        </ol>
        <div className="comparison-tutorial-actions">
          <Link className="career-primary" href="/sign-in">
            로그인, 회원가입
          </Link>
          {!started && (
            <button
              className="career-secondary"
              onClick={() => setStarted(true)}
              aria-expanded={started}
              aria-controls="comparison-tutorial-example"
            >
              역량 비교 해보기
            </button>
          )}
        </div>
      </section>
      {started && (
        <section
          id="comparison-tutorial-example"
          className="career-panel comparison-tutorial-example"
          aria-labelledby="comparison-example-title"
        >
          <span className="comparison-tutorial-label">비교 예시</span>
          <h2 id="comparison-example-title">{experienceJob.title}</h2>
          <p>
            예시 데이터로 보는 비교 화면입니다. 다각형의 각 점에 마우스를
            올리거나 점을 선택하면 LV를 확인할 수 있습니다.
          </p>
          <SavedLevelRadar levels={experienceLevels} />
          <div className="comparison-tutorial-actions">
            <Link className="career-primary" href="/sign-in">
              로그인하고 내 역량 비교
            </Link>
            <Link href="/jobs">채용 공고 보기</Link>
          </div>
        </section>
      )}
    </div>
  );
}
