"use client";
import Link from "next/link";
import { ArrowRight, FileText, BriefcaseBusiness } from "lucide-react";
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
          <span className="sky-eyebrow">경험에서 시작하는 커리어</span>
          <h1>
            관심 있는 공고에서
            <br />
            나의 가능성을 확인해요
          </h1>
          <p>
            GitHub와 PDF 이력서로 경험을 분석하고,
            <br />
            채용공고마다 필요한 역량과 비교해 보세요.
          </p>
          <Link className="cta" href="/analysis">
            내 경험 분석하기 <ArrowRight size={17} aria-hidden="true" />
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
                <h2>
                  <FileText size={20} aria-hidden="true" /> 경험을 담아주세요
                </h2>
                <p>GitHub 링크나 PDF 이력서 하나로 시작해요.</p>
              </div>
            </header>
            <p>
              자료는 여러 개 추가할 수 있어요. 분석이 끝나면 관심 있는 공고에서
              내 역량을 확인해요.
            </p>
            <Link href="/analysis">
              분석 시작하기 <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </section>
          <section className="home-panel">
            <header>
              <div>
                <span className="home-panel-eyebrow">02 · JOBS</span>
                <h2>
                  <BriefcaseBusiness size={20} aria-hidden="true" /> 공고에서
                  비교해요
                </h2>
                <p>채용공고는 로그인 없이도 둘러볼 수 있어요.</p>
              </div>
            </header>
            <p>
              공고를 먼저 살펴봐도 좋아요. 비교할 공고를 찾았다면 내 자료를
              추가해 보세요.
            </p>
            <Link href="/jobs">
              채용공고 둘러보기 <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </section>
        </div>
        <div id="market-preview">
          <LiveJobsSection />
        </div>
      </div>
    </>
  );
}
