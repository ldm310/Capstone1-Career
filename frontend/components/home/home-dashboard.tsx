"use client";
import Link from "next/link";
import {
  SkyBackground,
  SkyPlayback,
} from "@/components/landing/sky-background";
import { LiveJobsSection } from "@/components/landing/live-jobs-section";

export function HomeDashboard() {
  return (
    <>
      <section className="sky-hero career-home-hero home-greeting">
        <SkyBackground className="home-sky-photo" />
        <div className="home-width home-greeting-copy">
          <span className="sky-eyebrow">CAREER</span>
          <h1>채용공고 기반 역량 분석</h1>
          <p>
            GitHub와 PDF 이력서의 경험을 채용공고의 역량 키워드와 비교합니다.
          </p>
          <Link className="cta" href="/analysis">
            자료 분석
          </Link>
        </div>
        <SkyPlayback />
      </section>
      <div className="home-width home-dashboard">
        <div className="home-panels">
          <section className="home-panel">
            <header>
              <div>
                <span className="home-panel-eyebrow">01 · ANALYSIS</span>
                <h2>자료 분석</h2>
              </div>
            </header>
            <p>
              GitHub 링크 또는 PDF 이력서를 등록합니다. 자료는 1개 이상 추가할
              수 있습니다.
            </p>
            <Link className="home-panel-action" href="/analysis">
              분석 시작
            </Link>
          </section>
          <section className="home-panel">
            <header>
              <div>
                <span className="home-panel-eyebrow">02 · JOBS</span>
                <h2>채용공고</h2>
              </div>
            </header>
            <p>
              공고의 자격요건과 역량 키워드를 확인합니다. 공고 조회는 로그인
              없이 가능합니다.
            </p>
            <Link className="home-panel-action" href="/jobs">
              공고 목록
            </Link>
          </section>
        </div>
        <div className="home-market">
          <LiveJobsSection />
        </div>
      </div>
    </>
  );
}
