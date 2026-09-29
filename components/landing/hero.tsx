"use client";
import { Github } from "@/components/shared/github-icon";
import { motion } from "motion/react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Sparkles,
  Fingerprint,
  ChartNoAxesCombined,
  ArrowDown,
  CornerDownRight,
  FileText,
} from "lucide-react";
import { LinkButton, Tags } from "@/components/shared/primitives";
import type { getHeroPreview } from "@/lib/career-selectors";
export function Hero({
  preview,
}: {
  preview: ReturnType<typeof getHeroPreview>;
}) {
  return (
    <section className="hero section-width">
      <div className="hero-copy">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <div className="hero-eyebrow">
            <span className="status-dot" /> 내 경험에서 시작하는 다음 커리어{" "}
            <ArrowUpRight size={13} />
          </div>
          <h1>
            쌓아온 경험을,
            <br />
            다음 커리어의
            <br />
            <span>가능성으로.</span>
            <span className="hero-asterisk" aria-hidden="true">
              ✳
            </span>
          </h1>
          <p className="hero-description">
            내가 해온 일, 이제 역량으로 보여주세요.
          </p>
          <p className="hero-subcopy">
            시장이 원하는 역량과 내가 쌓아온 경험을 연결하세요.
            <br />
            당신의 GitHub, PDF, Markdown에서 다음 커리어의 방향을 찾습니다.
          </p>
          <div className="hero-ctas">
            <LinkButton href="/onboarding">
              내 역량 분석 시작하기 <ArrowRight size={17} />
            </LinkButton>
            <LinkButton href="/market" secondary>
              채용시장 살펴보기 <ArrowUpRight size={16} />
            </LinkButton>
          </div>
          <div className="hero-footnote">
            <span className="tiny-check">
              <Check size={11} />
            </span>{" "}
            모든 역량에는 근거가 필요하니까.{" "}
            <span className="dot-divider">·</span> 무료로 체험해 보세요
          </div>
        </motion.div>
      </div>
      <motion.div
        className="twin-visual"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <div className="visual-grid" />
        <div className="orbit orbit-one" />
        <div className="orbit orbit-two" />
        <div className="visual-caption">
          <span className="status-dot" /> 기록이 모여 선명해지는 나의 가능성
        </div>
        <div className="twin-node">
          <Fingerprint strokeWidth={1.1} size={62} />
          <strong>나의 Career</strong>
          <span>경험과 기록으로 연결된 나</span>
        </div>
        <div className="floating-card market-float">
          <div className="float-heading">
            <span className="icon-tile">
              <ChartNoAxesCombined size={16} />
            </span>
            <span>
              채용시장 동향<small>기업이 찾는 역량</small>
            </span>
            <span className="live-dot" />
          </div>
          <div className="mini-chart">
            {preview.market.map((skill) => (
              <div key={skill.skillId}>
                <span>{skill.name}</span>
                <i style={{ width: `${skill.demand}%` }} />
                <b>{skill.demand}%</b>
              </div>
            ))}
          </div>
        </div>
        <div className="floating-card evidence-float">
          <div className="float-heading">
            <Github size={18} />
            <span>
              내 역량 자료<small>{preview.evidenceTitle} / main</small>
            </span>
            <span className="check-circle">
              <Check size={12} />
            </span>
          </div>
          <Tags items={preview.evidenceSkills} />
          <div className="float-bottom">
            <span className="status-dot" /> 구현 근거 확인{" "}
            <span>체험 데이터</span>
          </div>
        </div>
        <div className="floating-card gap-float">
          <span className="eyebrow">보완할 역량</span>
          <strong>
            {preview.opportunity} <ArrowUpRight size={16} />
          </strong>
          <p>시장에서 찾는, 다음에 쌓을 역량</p>
          <div className="gap-dashes">
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="floating-card action-float">
          <span className="icon-tile green">
            <Sparkles size={19} />
          </span>
          <div>
            <small>나를 위한 추천 활동</small>
            <strong>만들고 배우며, 한 걸음 더.</strong>
          </div>
          <CornerDownRight size={19} />
        </div>
        <span className="visual-demo">
          체험 데이터 예시 · 실력 점수가 아닙니다
        </span>
      </motion.div>
    </section>
  );
}
export function SourceStrip() {
  return (
    <section className="source-strip section-width">
      <span>
        지금까지 해온 것,
        <br />
        <strong>자료 하나로 시작하세요.</strong>
      </span>
      <div>
        <Github size={24} /> GitHub 링크
      </div>
      <div>
        <FileText size={24} /> PDF
      </div>
      <div>
        <FileText size={24} /> Markdown
      </div>
    </section>
  );
}
export function HowItWorks() {
  return (
    <section className="how-section section-width" id="how-it-works">
      <div className="section-heading">
        <span className="eyebrow">무엇부터 준비할지 막막할 때</span>
        <h2>
          더 선명한 방향을,
          <br />
          하나의 경험부터.
        </h2>
        <p>시장이 원하는 것과 내가 해온 일을 연결합니다.</p>
      </div>
      <div className="steps-grid">
        {[
          {
            n: "01",
            title: "시장이 원하는 역량 확인",
            description:
              "실제 채용공고에서 반복되는 기술과 새롭게 떠오르는 역량을 확인하세요.",
            icon: ChartNoAxesCombined,
          },
          {
            n: "02",
            title: "내 경험 속 역량 발견",
            description:
              "코드, 경험, 학습 기록에서 발견한 역량을 출처와 함께 살펴보세요.",
            icon: Fingerprint,
          },
          {
            n: "03",
            title: "나를 위한 다음 활동",
            description:
              "부족한 역량을 채울 구체적인 행동을 실행하고 새로운 역량 근거를 쌓으세요.",
            icon: Sparkles,
          },
        ].map(({ n, title, description, icon: Icon }) => (
          <article key={n}>
            <div className="step-top">
              <span>{n}</span>
              <Icon size={24} />
            </div>
            <h3>{title}</h3>
            <p>{description}</p>
          </article>
        ))}
      </div>
      <div className="loop-note">
        <ArrowDown size={14} /> 새로운 활동이 근거가 되고, 다음 방향이 됩니다.
      </div>
    </section>
  );
}
