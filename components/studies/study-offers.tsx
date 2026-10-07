"use client";
import Link from "next/link";
import { ArrowRight, Route, Users } from "lucide-react";
import type { PublicJob } from "@/types/public-job";
import { studyOffers, tierLabels, type StudyTier } from "@/lib/study-prototype";
import { applicationKey, useStudies } from "./study-provider";

export function StudyOffers({
  job,
  tier,
}: {
  job: PublicJob;
  tier: StudyTier | null;
}) {
  const { state, ready, join } = useStudies();
  if (!tier)
    return (
      <section className="study-empty">
        <Route size={30} />
        <h3>나에게 맞는 스터디를 준비하고 있어요</h3>
        <p>
          지원 기록과 이 공고에서의 상대 수준을 확인한 뒤 같은 수준의 스터디만
          보여드려요.
        </p>
        <span className="study-pill">상대 수준 판정 대기</span>
        <p>
          현재는 판정 기준이 미정이에요. 예시 체험에서 참여 흐름을 살펴볼 수
          있어요.
        </p>
        <Link href="/jobs?demo=low">
          스터디 예시 체험하기 <ArrowRight size={16} />
        </Link>
      </section>
    );
  const applied = state.applied.includes(applicationKey(job.id, tier));
  if (!applied)
    return (
      <section className="study-empty">
        <Users size={30} />
        <h3>지원 완료를 확인하면 스터디를 볼 수 있어요</h3>
        <p>
          위에서 ‘지원했어요’를 눌러 주세요. 같은 공고·같은 수준의 스터디만
          안내해요.
        </p>
      </section>
    );
  return (
    <section className="study-offers">
      <div className="study-section-heading">
        <div>
          <span className={`study-tier ${tier}`}>
            {tierLabels[tier]} · 예시
          </span>
          <h2>이 공고를 함께 준비하는 스터디</h2>
          <p>
            {tier === "low"
              ? "프로젝트 적용 경험을 쌓으며 Middle을 준비해요."
              : tier === "middle"
                ? "개선·문제 해결 경험을 쌓으며 High를 준비해요."
                : "내 프로젝트에 맞는 심화 목표와 로드맵으로 준비해요."}
          </p>
        </div>
      </div>
      <div className="study-offer-grid">
        {studyOffers(job, tier).map((offer) => {
          const room = state.rooms.find(
            (r) => r.id === offer.id && r.tier === tier,
          );
          return (
            <article className="study-offer" key={offer.id}>
              <div className="study-offer-top">
                <span className={`study-tier ${tier}`}>{tierLabels[tier]}</span>
                <span>
                  <Users size={15} />
                  {room ? "나 1명 참여 중" : "혼자서도 시작 가능"}
                </span>
              </div>
              <h3>{offer.title}</h3>
              <p>{offer.description}</p>
              <div className="study-skill-tags">
                {job.skills?.map((skill) => (
                  <span key={skill}>{skill}</span>
                ))}
              </div>
              <p className="study-muted">
                한 명이어도 기다리지 않고 로드맵을 시작해요.
              </p>
              {room ? (
                <Link
                  className="study-primary"
                  href={`/studies?demo=${tier}&room=${encodeURIComponent(offer.id)}`}
                >
                  스터디 들어가기 <ArrowRight size={16} />
                </Link>
              ) : (
                <button
                  disabled={!ready}
                  className="study-primary"
                  onClick={() => join(offer)}
                >
                  참여 신청 <ArrowRight size={16} />
                </button>
              )}
            </article>
          );
        })}
      </div>
      <p className="study-muted">
        예시 스터디예요. 참여 신청과 활동은 이 브라우저에만 기록되며 다른
        사용자에게 전달되지 않아요.
      </p>
    </section>
  );
}
