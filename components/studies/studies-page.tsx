"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Users } from "lucide-react";
import {
  studyTier,
  studyDemoJobs,
  studyOffers,
  tierLabels,
} from "@/lib/study-prototype";
import { useStudies } from "./study-provider";
import { ExampleSwitcher } from "./example-switcher";
import { StudyRoom } from "./study-room";

export function StudiesPage() {
  const params = useSearchParams();
  const tier = studyTier(params.get("demo"));
  const roomId = params.get("room");
  const { state, ready, error } = useStudies();
  if (!tier)
    return (
      <section className="study-empty">
        <Users size={34} />
        <h2>내가 참여한 스터디를 한곳에</h2>
        <p>공고에서 지원을 확인하고, 내 수준에 맞는 스터디에 참여해 보세요.</p>
        <p className="study-muted">
          현재 실제 수준 판정과 멤버 연결은 준비 중이에요. 예시 공간에서
          로드맵·채팅·일정·자료 공유를 체험할 수 있어요.
        </p>
        <div className="study-empty-actions">
          <Link className="study-primary" href="/jobs">
            공고 찾아보기
          </Link>
          <Link href="/studies?demo=low">예시 스터디 기록 보기 →</Link>
        </div>
      </section>
    );
  const rooms = state.rooms.filter((r) => r.tier === tier);
  const room = rooms.find((r) => r.id === roomId);
  const job = studyDemoJobs.find((j) => j.id === room?.jobId);
  const offer = job
    ? studyOffers(job, tier).find((o) => o.id === room?.id)
    : undefined;
  return (
    <div>
      <ExampleSwitcher tier={tier} />
      {error && <p role="alert">{error}</p>}
      {!ready ? (
        <p role="status">스터디 기록을 불러오고 있어요…</p>
      ) : roomId ? (
        room && job && offer ? (
          <StudyRoom
            key={room.id}
            room={room}
            offer={offer}
            company={job.company}
            jobTitle={job.title}
          />
        ) : (
          <section className="study-empty">
            <h2>이 체험에서 참여한 스터디가 아니에요</h2>
            <Link href={`/studies?demo=${tier}`}>내 스터디 목록으로</Link>
          </section>
        )
      ) : (
        <>
          <div className="study-section-heading">
            <div>
              <h2>
                신청한 스터디 <span>{rooms.length}</span>
              </h2>
              <p>
                공고별로 참여한 {tierLabels[tier]} 스터디와 진행 상황을
                확인하세요.
              </p>
            </div>
            <Link href={`/jobs?demo=${tier}`}>
              스터디 찾아보기 <ArrowRight size={16} />
            </Link>
          </div>
          {!rooms.length ? (
            <section className="study-empty">
              <Users size={30} />
              <h3>아직 참여한 스터디가 없어요</h3>
              <p>관심 공고에 지원했는지 확인한 뒤 스터디를 선택해 보세요.</p>
              <Link className="study-primary" href={`/jobs?demo=${tier}`}>
                공고에서 스터디 찾기
              </Link>
            </section>
          ) : (
            <div className="study-offer-grid">
              {rooms.map((item) => {
                const itemJob = studyDemoJobs.find((j) => j.id === item.jobId);
                const itemOffer =
                  itemJob &&
                  studyOffers(itemJob, tier).find((o) => o.id === item.id);
                if (!itemJob || !itemOffer) return null;
                const completed = item.completed.filter(
                  (i) => i < itemOffer.roadmap.length,
                ).length;
                return (
                  <article className="study-offer" key={item.id}>
                    <span className={`study-tier ${tier}`}>
                      {tierLabels[tier]} · 예시 참여
                    </span>
                    <p>
                      {itemJob.company} · {itemJob.title}
                    </p>
                    <h3>{itemOffer.title}</h3>
                    <div className="study-progress-label">
                      <span>나의 진행</span>
                      <strong>
                        {completed}/{itemOffer.roadmap.length}개
                      </strong>
                    </div>
                    <progress
                      className="study-progress"
                      aria-label={`${itemOffer.title} 진행률`}
                      max={itemOffer.roadmap.length}
                      value={completed}
                    />
                    <p className="study-muted">
                      나 1명 · 개인 로드맵 진행 가능
                    </p>
                    <Link
                      className="study-primary"
                      href={`/studies?demo=${tier}&room=${encodeURIComponent(item.id)}`}
                    >
                      이어서 준비하기 <ArrowRight size={16} />
                    </Link>
                  </article>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
