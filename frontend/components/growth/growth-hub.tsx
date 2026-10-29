"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { LearningPath } from "./learning-path";
import { DetailDialog } from "./detail-dialog";
import { SkillList, skillCardItems } from "./skill-card-grid";
import { scoreTier, scoreTiers } from "@/lib/growth/score";
import { ArrowRight } from "lucide-react";
import { criteria, levelNames, requirement } from "@/lib/growth/catalog";
import { emptyGrowth, type GrowthState, type Level } from "@/types/growth";
import type { Finding } from "@/types/workspace";
import { mergeReviews } from "@/lib/growth/model";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
export function GrowthHub({
  preparation = false,
  role = "data",
  findings = [],
  targets = ["SQL", "Python", "PostgreSQL", "Airflow", "Spark", "Docker"],
}: {
  preparation?: boolean;
  role?: string;
  findings?: Finding[];
  targets?: string[];
}) {
  const [g, setG] = useState<GrowthState>(structuredClone(emptyGrowth));
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [selected, setSelected] = useState<string | null>(null),
    [filter, setFilter] = useState("all");
  useEffect(() => {
    let active = true;
    fetch("/api/growth")
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw Error(d.error);
        if (active) setG(d.growth);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [findings]);
  async function act(body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const r = await fetch("/api/growth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error);
      setG(d.growth);
      setMessage("저장했어요.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }
  const growth = mergeReviews(g, findings),
    visible = growth.reviews.filter((r) => r.status !== "excluded");
  const names = [
    ...new Set([
      ...visible.map((r) => r.skill),
      ...targets.filter(
        (s) =>
          !growth.reviews.some((r) => r.skill === s && r.status === "excluded"),
      ),
    ]),
  ];
  const cards = skillCardItems(names, visible, findings);
  if (loading) return <LoadingSpinner />;
  return (
    <div className="growth-hub">
      <div aria-live="polite">
        {message && <p className="career-status">{message}</p>}
        {error && (
          <p role="alert" className="career-error">
            {error}{" "}
            <button onClick={() => window.location.reload()}>
              다시 불러오기
            </button>
          </p>
        )}
      </div>
      {preparation && (
        <LearningPath
          role={role}
          reviews={visible}
          tasks={g.tasks}
          onSelect={setSelected}
        />
      )}
      <section className={`career-panel${preparation ? "" : " skill-panel"}`}>
        <div className="growth-section-heading">
          <div>
            <h2>{preparation ? "기술별 다음 과제" : "찾은 기술"}</h2>
            {!findings.length && (
              <p>
                아직 자료가 없어요. <Link href="/my-data">자료 추가 →</Link>
              </p>
            )}
          </div>
          <label>
            보기
            <select
              aria-label="보기"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">모든 기술</option>
              <option value="pending">확인 전</option>
              <option value="unknown">자료 부족</option>
              {preparation
                ? [1, 2, 3].map((n) => (
                    <option key={n} value={String(n)}>
                      LV{n}
                    </option>
                  ))
                : scoreTiers.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name}
                    </option>
                  ))}
            </select>
          </label>
        </div>
        {!preparation ? (
          <SkillList
            items={cards.filter(
              (c) =>
                filter === "all" ||
                (filter === "pending"
                  ? c.review?.status === "pending"
                  : filter === "unknown"
                    ? !c.evidence.length
                    : scoreTier(c.score).name === filter),
            )}
            onSelect={setSelected}
          />
        ) : (
          <div className="growth-cards">
            {names
              .filter((s) => {
                const r = visible.find((r) => r.skill === s);
                return (
                  filter === "all" ||
                  (filter === "pending"
                    ? r?.status === "pending"
                    : filter === "unknown"
                      ? !r?.level
                      : String(r?.level) === filter)
                );
              })
              .map((skill) => {
                const r = visible.find((r) => r.skill === skill);
                const next = ((r?.level || 0) + 1) as Level;
                return (
                  <article className="growth-skill card-click" key={skill}>
                    <div className="growth-section-heading">
                      <h3>{skill}</h3>
                      {r?.status === "pending" && (
                        <span className="growth-tag">확인 전</span>
                      )}
                    </div>
                    <p className="growth-current">
                      현재 수준
                      <br />
                      <strong>
                        {r?.level
                          ? `LV${r.level} ${levelNames[r.level]}`
                          : "자료 부족"}
                      </strong>
                    </p>
                    <div className="growth-levels">
                      {([1, 2, 3] as Level[]).map((l) => (
                        <span
                          key={l}
                          className={(r?.level || 0) >= l ? "met" : ""}
                        >
                          LV{l}
                          <small>{levelNames[l]}</small>
                        </span>
                      ))}
                    </div>
                    <div className="growth-next">
                      <small>다음 준비</small>
                      <strong>
                        {next <= 3 && criteria[skill]
                          ? `LV${next} ${levelNames[next]}`
                          : r?.level === 3
                            ? "공고와 비교해 보세요"
                            : "기준 준비 중"}
                      </strong>
                    </div>
                    <button
                      className="card-link"
                      onClick={() => setSelected(skill)}
                      aria-label={`${skill} 자세히`}
                    >
                      자세히 <ArrowRight size={16} />
                    </button>
                  </article>
                );
              })}
          </div>
        )}
        {!names.length && <p>자료를 추가하면 기술이 표시돼요.</p>}
      </section>
      {selected && (
        <DetailDialog onClose={() => setSelected(null)}>
          <section className="career-panel" aria-label={`${selected} 상세`}>
            <button className="growth-close" onClick={() => setSelected(null)}>
              닫기 ×
            </button>
            <h2>{selected}</h2>
            {(() => {
              const card = cards.find((c) => c.skill === selected);
              return card ? (
                <p className="skill-dialog-level">
                  <b>LV {card.score}</b> {scoreTier(card.score).name}
                </p>
              ) : null;
            })()}
            {(() => {
              const r = cards.find((c) => c.skill === selected)?.review;
              return (
                <>
                  {r?.reason && <p>{r.reason}</p>}
                  {r && (
                    <>
                      <div className="growth-actions">
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act({
                              action: "review",
                              skill: selected,
                              name: selected,
                              status: "confirmed",
                            })
                          }
                        >
                          확인
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => {
                            void act({
                              action: "review",
                              skill: selected,
                              name: selected,
                              status: "excluded",
                            });
                            setSelected(null);
                          }}
                        >
                          제외
                        </button>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act({
                              action: "review",
                              skill: selected,
                              name: selected,
                              status: "appeal",
                            })
                          }
                        >
                          재검토 요청
                        </button>
                      </div>
                      <label>
                        기술 이름 수정
                        <select
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) {
                              void act({
                                action: "review",
                                skill: selected,
                                name: e.target.value,
                                status: "edited",
                              });
                              setSelected(null);
                            }
                          }}
                        >
                          <option value="" disabled>
                            기술 선택
                          </option>
                          {Object.keys(criteria).map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                      </label>
                    </>
                  )}
                  {!r && <Link href="/my-data">자료 추가 →</Link>}
                  <h3>단계별 기준</h3>
                  {([1, 2, 3] as Level[]).map((l) => (
                    <div className="growth-criterion" key={l}>
                      <strong>
                        LV{l} {levelNames[l]}
                      </strong>
                      <p>{requirement(selected, l)}</p>
                    </div>
                  ))}
                </>
              );
            })()}
          </section>
        </DetailDialog>
      )}
    </div>
  );
}
